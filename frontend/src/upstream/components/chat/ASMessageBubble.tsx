import { ReplyFinishedReason } from '@agentscope-ai/agentscope/event';
import type {
	ContentBlock,
	DataBlock,
	Msg,
	TextBlock,
	ThinkingBlock,
	ToolCallBlock,
	ToolResultBlock,
} from '@agentscope-ai/agentscope/message';
import {
	ArrowDown,
	ArrowUp,
	Check,
	CheckCircle,
	ChevronRight,
	CirclePlay,
	Copy,
	Download,
	FileText,
	FileVideo2,
	Loader2,
	MessageSquareText,
	Square,
	TriangleAlert,
	X,
} from 'lucide-react';
import * as mime from 'mime-types';
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { renderToolCall } from './tool-renderers';
import { countDiffStats, DiffStats, getResultDiff } from './tool-renderers/_shared';
import type { TFunction, ToolCallWithResult } from './tool-renderers/types';
import { Markdown } from '@upstream/components/markdown';
import { Alert, AlertDescription, AlertTitle } from '@upstream/components/ui/alert';
import {
	Attachment,
	AttachmentContent,
	AttachmentDescription,
	AttachmentGroup,
	AttachmentMedia,
	AttachmentTitle,
} from '@upstream/components/ui/attachment.tsx';
import { Badge } from '@upstream/components/ui/badge';
import { Button } from '@upstream/components/ui/button';
import { Input } from '@upstream/components/ui/input';
import { Bubble, BubbleContent } from '@upstream/components/ui/bubble.tsx';
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from '@upstream/components/ui/collapsible.tsx';
import { Message, MessageFooter, MessageContent } from '@upstream/components/ui/message';
import { useAudioBlock, useReplayController } from '@upstream/context/AudioContext';
import { useTranslation } from '@upstream/i18n/useI18n';
import { cn } from '@upstream/lib/utils';
import { formatNumber, formatTime } from '@upstream/utils/common';
import { toast } from 'sonner';
import { ContextMenu as ContextMenuPrimitive } from 'radix-ui';
import { QuoteBadge } from './QuoteBadge';
import { messageQuoteKey, messageReferenceFromSelection, readQuoteReferences, readQuotedBody, type MessageQuote, type QuoteReference } from './quote-references';
import { captureRenderedSelection, restoreRenderedSelection } from './rendered-selection';
import { addMessageHighlight } from './message-highlight';
import 'streamdown/styles.css';

/**
 * A run of *consecutive* tool calls (of any name) collapsed into a single
 * container, each call paired to its result. The one aggregated summary/fold
 * renders here; every call inside is dispatched to its dedicated per-tool
 * renderer via `renderToolCall`.
 */
interface ToolCallGroupBlock {
	type: 'tool_call_group';
	calls: ToolCallWithResult[];
	created_at?: string;
	finished_at?: string;
}

type ExtendedContentBlock = ContentBlock | ToolCallGroupBlock;

function placeCommentHost(line: Element, host: HTMLElement) {
	if (line.tagName === 'LI') { line.append(host); return; }
	let anchor = line;
	while (anchor.nextElementSibling?.hasAttribute('data-quote-comment-host')) anchor = anchor.nextElementSibling;
	anchor.after(host);
}

/**
 * Pair every tool_call with its tool_result (by id) and collect *consecutive*
 * tool calls into a single `tool_call_group`, regardless of tool name — so a
 * run like `[Read, Read, Edit, some_mcp_tool]` becomes one collapsible
 * container. Non-tool blocks (text, thinking, data, ...) break the run and
 * pass through unchanged at their original position.
 *
 * Results may arrive after their calls — concurrent tool use lays content out
 * as `[call_A, call_B, result_A, result_B]` — so calls are paired by id in a
 * first pass before the run is assembled.
 */
function groupToolCalls(content: ContentBlock[]): ExtendedContentBlock[] {
	// Pass 1: pair calls ↔ results by id; remember non-tool blocks in order.
	const callMap = new Map<string, ToolCallWithResult>();
	const orphanResults: ToolResultBlock[] = [];
	const ordering: Array<{ type: 'tool'; id: string } | { type: 'other'; block: ContentBlock }> =
		[];

	for (const block of content) {
		if (block.type === 'tool_call') {
			callMap.set(block.id, { call: block });
			ordering.push({ type: 'tool', id: block.id });
		} else if (block.type === 'tool_result') {
			const matching = callMap.get(block.id);
			if (matching) matching.result = block;
			else orphanResults.push(block);
		} else {
			ordering.push({ type: 'other', block });
		}
	}

	// Pass 2: walk the ordering, accumulating consecutive calls into one group.
	const result: ExtendedContentBlock[] = [];
	let current: ToolCallWithResult[] = [];
	const flush = () => {
		if (current.length === 0) return;
		result.push({ type: 'tool_call_group', calls: current });
		current = [];
	};

	for (const item of ordering) {
		if (item.type === 'other') {
			flush();
			result.push(item.block);
		} else {
			const entry = callMap.get(item.id);
			if (entry) current.push(entry);
		}
	}
	flush();

	// Orphan results (no matching call) — surface each as its own group.
	for (const block of orphanResults) {
		result.push({
			type: 'tool_call_group',
			calls: [
				{
					call: {
						type: 'tool_call',
						id: block.id,
						name: block.name,
						input: '',
						state: 'finished' as const,
						created_at: block.created_at,
						finished_at: block.finished_at,
					},
					result: block,
				},
			],
		});
	}

	return result;
}

const AUDIO_WAVE_LINES: Array<{ x: number; y1: number; y2: number }> = [
	{ x: 2, y1: 10, y2: 13 },
	{ x: 6, y1: 6, y2: 17 },
	{ x: 10, y1: 3, y2: 21 },
	{ x: 14, y1: 8, y2: 15 },
	{ x: 18, y1: 5, y2: 18 },
	{ x: 22, y1: 10, y2: 13 },
];

function AudioWave({ isPlaying = true, className }: { isPlaying?: boolean; className?: string }) {
	return (
		<>
			{isPlaying && (
				<style>{`
					@keyframes audioWave {
						0%, 100% { transform: scaleY(1); }
						50%      { transform: scaleY(0.3); }
					}
				`}</style>
			)}
			<svg
				xmlns="http://www.w3.org/2000/svg"
				width="24"
				height="24"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				strokeWidth={2}
				strokeLinecap="round"
				strokeLinejoin="round"
				className={className}
			>
				{AUDIO_WAVE_LINES.map(({ x, y1, y2 }, i) => (
					<line
						key={x}
						x1={x}
						x2={x}
						y1={y1}
						y2={y2}
						style={{
							transformOrigin: `${x}px 12px`,
							animation: isPlaying
								? `audioWave 0.8s ease-in-out ${i * 0.12}s infinite`
								: 'none',
						}}
					/>
				))}
			</svg>
		</>
	);
}

/**
 * Inline audio control rendered *inside* the time/usage Badge so the play
 * icon visually merges into the same chip rather than floating as its own
 * pill.
 */
function AudioInlineControl({ block }: { block: DataBlock }) {
	const { t } = useTranslation();
	const audioState = useAudioBlock(block.id);
	const replayController = useReplayController();
	const audioRef = useRef<HTMLAudioElement | null>(null);
	const [isPlaying, setIsPlaying] = useState(false);

	const isStreaming = audioState?.status === 'streaming';

	// Don't build the giant base64 data URL while bytes are still streaming —
	// it would re-allocate on every DATA_BLOCK_DELTA. Live playback during
	// that window is handled by the manager's WavStreamPlayer; we only need
	// `src` for replay after the stream ends (or for historical messages).
	let src: string | null = null;
	if (!isStreaming) {
		if (audioState?.url) {
			src = audioState.url;
		} else if (block.source.type === 'url') {
			src = block.source.url;
		} else if (block.source.type === 'base64' && block.source.data) {
			src = `data:${block.source.media_type};base64,${block.source.data}`;
		}
	}

	// Reset the hidden <audio> when the source URL changes (e.g. streaming
	// just transitioned to a Blob URL). Without an explicit load() some
	// browsers keep the previous (or empty) source bound to the element.
	useEffect(() => {
		const el = audioRef.current;
		if (!el || !src) return;
		setIsPlaying(false);
		el.load();
	}, [src]);

	// Pause when a newer reply interrupts this block's playback.
	const interruptCount = audioState?.interruptCount ?? 0;
	useEffect(() => {
		if (interruptCount === 0) return;
		const el = audioRef.current;
		if (el && !el.paused) {
			el.pause();
		}
	}, [interruptCount]);

	if (isStreaming) {
		return <AudioWave isPlaying className="ml-1" />;
	}

	if (!src) return null;

	const toggle = async () => {
		const el = audioRef.current;
		if (!el) return;
		if (el.paused) {
			replayController?.play(el);
			try {
				await el.play();
			} catch (err) {
				console.error('Audio playback failed', err);
			}
		} else {
			el.pause();
			replayController?.stop();
		}
	};

	return (
		<>
			<button
				type="button"
				onClick={toggle}
				aria-label={
					isPlaying ? t('messageBubble.pauseAudio') : t('messageBubble.playAudio')
				}
				className="ml-1 inline-flex cursor-pointer items-center transition-opacity hover:opacity-70"
			>
				{isPlaying ? (
					<AudioWave isPlaying className="size-3" />
				) : (
					<CirclePlay className="size-3" />
				)}
			</button>
			<audio
				ref={audioRef}
				src={src}
				preload="auto"
				onPlay={() => setIsPlaying(true)}
				onPause={() => setIsPlaying(false)}
				onEnded={() => setIsPlaying(false)}
			/>
		</>
	);
}

const MCP_TOOL_PREFIX = 'mcp__';

// Task-management tools are all surfaced under one "updated todos" summary.
const TODO_TOOLS = new Set(['TaskGet', 'TaskUpdate', 'TaskList', 'TaskCreate']);

/**
 * Bucket a group's calls into per-category counts and total inserted/deleted
 * lines (from Edit/Write result diffs), then build the localized collapsible
 * title. Categories are appended in a fixed order — Bash, Read, Edit/Write,
 * Search (Grep/Glob), Todo, MCP — each omitted when its count is zero. If
 * nothing matches a known category, a generic "called N tools" fallback is used.
 */
function summarizeToolGroup(calls: ToolCallWithResult[], t: TFunction) {
	let nBash = 0;
	let nRead = 0;
	let nEdit = 0;
	let nSearch = 0;
	let nTodo = 0;
	let nMCP = 0;
	let insertions = 0;
	let deletions = 0;

	for (const { call, result } of calls) {
		const name = call.name;
		if (name === 'Bash') {
			nBash += 1;
		} else if (name === 'Read') {
			nRead += 1;
		} else if (name === 'Edit' || name === 'Write') {
			nEdit += 1;
			// Sum the real +/- line changes from the backend-provided diff.
			const diff = result ? getResultDiff(result) : undefined;
			if (diff) {
				const stats = countDiffStats(diff);
				insertions += stats.insertions;
				deletions += stats.deletions;
			}
		} else if (name === 'Grep' || name === 'Glob') {
			nSearch += 1;
		} else if (TODO_TOOLS.has(name)) {
			nTodo += 1;
		} else if (name.startsWith(MCP_TOOL_PREFIX)) {
			nMCP += 1;
		}
	}

	const parts: string[] = [];
	if (nBash > 0) parts.push(t('tool.summary.bash', { count: nBash }));
	if (nRead > 0) parts.push(t('tool.summary.read', { count: nRead }));
	if (nEdit > 0) parts.push(t('tool.summary.edit', { count: nEdit }));
	if (nSearch > 0) parts.push(t('tool.summary.search', { count: nSearch }));
	if (nTodo > 0) parts.push(t('tool.summary.todo', { count: nTodo }));
	if (nMCP > 0) parts.push(t('tool.summary.mcp', { count: nMCP }));

	const joined =
		parts.length > 0
			? parts.join(t('tool.summary.separator'))
			: t('tool.summary.fallback', { count: calls.length });
	// Sentence-case only the very first letter (each i18n part is lower-cased
	// so commas don't introduce mid-sentence capitals in English; a no-op for
	// scripts without letter case such as Chinese).
	const title = joined.length > 0 ? joined[0].toUpperCase() + joined.slice(1) : joined;

	return { title, insertions, deletions };
}

interface MessageBubbleProps {
	message: Msg;
	onQuote?: (reference: QuoteReference) => boolean | void;
	onOpenReference?: (reference: QuoteReference) => void;
	annotations?: MessageQuote[];
	activeAnnotationKey?: string | null;
	onUserConfirm: (
		toolCallBlock: ToolCallBlock,
		confirm: boolean,
		replyId: string,
		rules?: ToolCallBlock['suggested_rules'],
	) => void;
}

/**
 * A message bubble component that displays a chat message.
 *
 * Running state is derived from `message.finished_at`: a missing or null
 * `finished_at` means the agent is still producing this reply. The bottom
 * status row shows a single left-aligned badge laid out as
 * `[state-icon] [duration] [↑in ↓out]`:
 *   - State icon: spinning `Loader2` while running, static `CheckCircle`
 *     once finished.
 *   - Duration is `now - created_at` while running (ticking each second),
 *     `finished_at - created_at` once complete.
 *   - Token counts only appear once `usage` is populated with non-zero
 *     values — typically after the message finishes.
 *
 * When `content` is empty and the message is still running, the bubble
 * body is omitted entirely so only the bottom status row renders.
 */
export function ASMessageBubble({ message, onQuote, onOpenReference, annotations, activeAnnotationKey }: MessageBubbleProps) {
	const isUser = message.role === 'user';
	const references = isUser ? readQuoteReferences(message.metadata) : [];
	const quotedBody = references.length ? readQuotedBody(message.metadata) : null;
	const [selection, setSelection] = useState<{ blockIndex: number; start: number; end: number; text: string; range: Range } | null>(null);
	const [quoteComment, setQuoteComment] = useState('');
	const [editorHost, setEditorHost] = useState<HTMLElement | null>(null);
	const commentInputRef = useRef<HTMLInputElement>(null);
	const [annotationHosts, setAnnotationHosts] = useState<Array<{ host: HTMLElement; reference: MessageQuote }>>([]);
	const textRoots = useRef(new Map<number, HTMLElement>());
	useEffect(() => () => editorHost?.remove(), [editorHost]);
	useEffect(() => {
		const hosts: Array<{ host: HTMLElement; reference: MessageQuote }> = [];
		const cleanup: Array<() => void> = [];
		for (const reference of annotations ?? []) {
			const root = textRoots.current.get(reference.block_index)?.querySelector<HTMLElement>('.cn-markdown');
			if (!root) continue;
			const range = restoreRenderedSelection(root, { start: reference.start, end: reference.end, text: reference.selected_text });
			if (!range) continue;
			cleanup.push(addMessageHighlight(range));
			if (messageQuoteKey(reference) !== activeAnnotationKey || !reference.comment) continue;
			const end = range.endContainer instanceof Element ? range.endContainer : range.endContainer.parentElement;
			const line = end?.closest('p, li, pre, blockquote, table') ?? root;
			const host = document.createElement('div');
			host.dataset.quoteCommentHost = 'true';
			placeCommentHost(line, host);
			hosts.push({ host, reference });
		}
		setAnnotationHosts(hosts);
		return () => { cleanup.forEach((remove) => remove()); hosts.forEach(({ host }) => host.remove()); };
	}, [annotations, activeAnnotationKey, message.content]);
	useEffect(() => editorHost && selection ? addMessageHighlight(selection.range) : undefined, [editorHost, selection]);
	const { t } = useTranslation();

	const isRunning = !message.finished_at;
	const hasUsage =
		!!message.usage &&
		((message.usage.input_tokens ?? 0) > 0 || (message.usage.output_tokens ?? 0) > 0);

	// Tick once per second while running so the elapsed time updates live.
	const [now, setNow] = useState(() => Date.now());
	useEffect(() => {
		if (!isRunning) return;
		const id = setInterval(() => setNow(Date.now()), 1000);
		return () => clearInterval(id);
	}, [isRunning]);

	// Audio data blocks are rendered in the footer;
	// For role="user" messages, the data blocks are rendered as attachments in the
	// footer, while for role="assistant" messages, the data is rendered in its
	// original position
	const audioBlocks = message.content.filter(
		(b): b is DataBlock => b.type === 'data' && b.source.media_type.split('/')[0] === 'audio',
	);

	const displayContent = quotedBody !== null ? [
		...message.content.filter((block) => block.type !== 'text'),
		...(quotedBody ? [{ ...message.content.find((block) => block.type === 'text'), type: 'text' as const, text: quotedBody } as TextBlock] : []),
	] : message.content;
	const blocks = groupToolCalls(displayContent);
	const captureSelection = (element: HTMLElement, block: ExtendedContentBlock) => {
		if (isUser || isRunning || !onQuote || block.type !== 'text') { setSelection(null); setEditorHost(null); return; }
		const selected = window.getSelection();
		if (!selected || selected.isCollapsed || !selected.anchorNode || !selected.focusNode ||
			!element.contains(selected.anchorNode) || !element.contains(selected.focusNode)) { setSelection(null); setEditorHost(null); return; }
		const root = element.querySelector<HTMLElement>('.cn-markdown');
		const range = selected.getRangeAt(0).cloneRange();
		const position = root && captureRenderedSelection(root, range);
		if (!position) { setSelection(null); setEditorHost(null); return; }
		const blockIndex = message.content.findIndex((item) => item.id === block.id);
		if (blockIndex < 0) { setSelection(null); setEditorHost(null); return; }
		setSelection({ blockIndex, ...position, range });
	};
	const beginQuote = () => {
		if (!selection) return;
		if (selection.text.length > 2000) { toast.error('引用最多 2000 字，请缩小选择范围'); return; }
		setQuoteComment('');
		const end = selection.range.endContainer instanceof Element ? selection.range.endContainer : selection.range.endContainer.parentElement;
		const line = end?.closest('p, li, pre, blockquote, table') ?? textRoots.current.get(selection.blockIndex);
		if (!line) return;
		const host = document.createElement('div');
		host.dataset.quoteCommentHost = 'true';
		placeCommentHost(line, host);
		setEditorHost(host);
	};
	const addQuote = () => {
		if (!selection || !onQuote) return;
		const accepted = onQuote(messageReferenceFromSelection(message.id, selection.blockIndex, selection.start, selection.end, selection.text, quoteComment.trim()));
		if (accepted === false) return;
		setSelection(null);
		setEditorHost(null);
		setQuoteComment('');
		window.getSelection()?.removeAllRanges();
	};
	const cancelQuote = () => { setSelection(null); setEditorHost(null) };

	// A fatal error terminated this reply. ``finished_reason`` / ``error`` are
	// reply-level fields set by ``appendEvent`` on a ``REPLY_END`` with
	// ``finished_reason === ReplyFinishedReason.ERROR`` — they are NOT content
	// blocks, so the body above is always genuine agent output. Rendered as a
	// separate alert below the body.
	const errorInfo = message.error;
	const isError = message.finished_reason === ReplyFinishedReason.ERROR || !!errorInfo;
	const isInterrupted = message.finished_reason === ReplyFinishedReason.INTERRUPTED;

	const startMs = new Date(message.created_at).getTime();
	const endMs = isRunning ? now : new Date(message.finished_at!).getTime();
	const elapsedSeconds = Math.max(0, (endMs - startMs) / 1000);
	const elapsedText = formatTime(elapsedSeconds);
	const messageText = displayContent
		.filter((block): block is TextBlock => block.type === 'text')
		.map((block) => block.text)
		.join('\n\n');
	const timestamp = isUser ? message.created_at : message.finished_at;
	const messageTime = timestamp ? new Date(timestamp) : null;
	const validMessageTime = messageTime && !Number.isNaN(messageTime.getTime()) ? messageTime : null;

	async function copyMessage() {
		try {
			await navigator.clipboard.writeText(messageText);
			toast.success('已复制消息');
		} catch {
			toast.error('复制失败，请重试');
		}
	}

	function exportMarkdown() {
		const blob = new Blob([messageText], { type: 'text/markdown;charset=utf-8' });
		const url = URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = `message-${message.id}.md`;
		link.click();
		setTimeout(() => URL.revokeObjectURL(url), 0);
	}

	return (
		<Message align={isUser ? 'end' : 'start'} data-role={message.role}>
			<MessageContent>
				{blocks
					.filter((block) => block.type !== 'data')
					.map((block, index) => (
						<Bubble key={index} variant={isUser ? 'muted' : 'ghost'}>
							<BubbleContent>
								{isUser && index === 0 && references.length > 0 && <div className="mb-2 flex flex-wrap gap-1.5">{references.map((reference, referenceIndex) =>
									<QuoteBadge key={referenceIndex} reference={reference} onOpen={() => onOpenReference?.(reference)} />
								)}</div>}
								<ContextMenuPrimitive.Root>
									<ContextMenuPrimitive.Trigger asChild>
										<div data-quote-block-index={message.content.findIndex((item) => item.id === ('id' in block ? block.id : undefined))}
											ref={(node) => { const blockIndex = message.content.findIndex((item) => item.id === ('id' in block ? block.id : undefined)); if (blockIndex >= 0) { if (node) textRoots.current.set(blockIndex, node); else textRoots.current.delete(blockIndex) } }}
											onContextMenu={(event) => captureSelection(event.currentTarget, block)}><ASBlock block={block} /></div>
									</ContextMenuPrimitive.Trigger>
									<ContextMenuPrimitive.Portal><ContextMenuPrimitive.Content onCloseAutoFocus={(event) => { if (editorHost) { event.preventDefault(); commentInputRef.current?.focus() } }} className="floating-surface z-50 min-w-(--menu-min-width) p-(--menu-padding)">
										<ContextMenuPrimitive.Item disabled={!selection || block.type !== 'text'} onSelect={beginQuote} className="flex cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-hidden focus:bg-accent data-disabled:opacity-50"><MessageSquareText className="size-4" />评论</ContextMenuPrimitive.Item>
										<ContextMenuPrimitive.Item disabled={!selection || block.type !== 'text'} onSelect={() => { if (selection) void navigator.clipboard.writeText(selection.text).then(() => toast.success('已复制')).catch(() => toast.error('复制失败，请重试')) }} className="flex cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-hidden focus:bg-accent data-disabled:opacity-50"><Copy className="size-4" />复制</ContextMenuPrimitive.Item>
									</ContextMenuPrimitive.Content></ContextMenuPrimitive.Portal>
								</ContextMenuPrimitive.Root>
							</BubbleContent>
						</Bubble>
					))}
				{isUser && references.length > 0 && blocks.every((block) => block.type === 'data') &&
					<Bubble variant="muted"><BubbleContent><div className="flex flex-wrap gap-1.5">{references.map((reference, index) =>
						<QuoteBadge key={index} reference={reference} onOpen={() => onOpenReference?.(reference)} />
					)}</div></BubbleContent></Bubble>}
				{selection && editorHost && createPortal(
					<div className="mt-1 flex w-full min-w-0 items-center gap-1 border-l-2 border-[var(--message-quote-accent)] bg-[var(--message-quote-fill)] px-2 py-1">
						<Input ref={commentInputRef} aria-label="引用评论" autoFocus maxLength={2000} className="h-8 min-w-0 flex-1 border-0 bg-transparent shadow-none focus-visible:ring-0" value={quoteComment} onChange={(event) => setQuoteComment(event.target.value)} placeholder="添加评论…" onKeyDown={(event) => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) { event.preventDefault(); addQuote() } else if (event.key === 'Escape') cancelQuote() }} />
						<Button type="button" variant="ghost" size="icon-xs" aria-label="取消引用" title="取消引用" onClick={cancelQuote}><X /></Button>
						<Button type="button" variant="ghost" size="icon-xs" aria-label="加入提问" title="加入提问" onClick={addQuote}><Check /></Button>
					</div>, editorHost,
				)}
				{annotationHosts.map(({ host, reference }, index) => createPortal(
					<div className="mt-1 border-l-2 border-[var(--message-quote-accent)] bg-[var(--message-quote-fill)] px-2 py-1 text-sm" aria-label="引用评论">{reference.comment}</div>, host, `${reference.source_message_id}:${reference.block_index}:${reference.start}:${index}`,
				))}
				{isError && (
					<Alert
						variant="destructive"
						className="m-2 w-[calc(100%-1rem)]"
					>
						<TriangleAlert />
						<AlertTitle>{t('messageBubble.error.title')}</AlertTitle>
						<AlertDescription>
							{t(`messageBubble.error.${errorInfo?.type ?? 'unknown'}`, {
								defaultValue:
									errorInfo?.message ?? t('messageBubble.error.unknown'),
							})}
						</AlertDescription>
					</Alert>
				)}
				{blocks.some((block) => block.type === 'data') && (
					<AttachmentGroup className="max-w-full">
						{blocks
							.filter((block) => block.type === 'data')
							.map((block, index) => (
								<ASBlock block={block} key={index} />
							))}
					</AttachmentGroup>
				)}
				{(!isUser || messageText) && (
					<MessageFooter className="-mt-1.5 flex items-center gap-1">
						{!isUser && (
						<Badge
							className="font-mono"
							variant="secondary"
							aria-label={isRunning ? t('messageBubble.running') : isInterrupted ? t('messageBubble.stopped') : undefined}
						>
							{isRunning ? (
								<Loader2 data-icon="inline-start" className="animate-spin" />
							) : isInterrupted ? (
								<Square data-icon="inline-start" />
							) : (
								<CheckCircle data-icon="inline-start" />
							)}
							{isInterrupted && <span>{t('messageBubble.stopped')}</span>}
							<span className="tabular-nums tracking-tighter">{elapsedText}</span>
							{hasUsage && (
								<>
									<ArrowUp data-icon="inline-start" className="ml-1" />
									<span className="tabular-nums">
										{formatNumber(message.usage?.input_tokens ?? 0)}
									</span>
									<ArrowDown data-icon="inline-start" className="ml-1" />
									<span className="tabular-nums">
										{formatNumber(message.usage?.output_tokens ?? 0)}
									</span>
								</>
							)}
							{audioBlocks.map((block) => (
								<AudioInlineControl key={block.id} block={block} />
							))}
						</Badge>
						)}
						{messageText && (isUser || !isRunning) && (
							<div className="flex items-center gap-0.5">
								<Button variant="ghost" size="icon-xs" aria-label="复制消息" title="复制消息" onClick={() => void copyMessage()}>
									<Copy />
								</Button>
								{!isUser && (
									<Button variant="ghost" size="icon-xs" aria-label="导出 Markdown" title="导出 Markdown" onClick={exportMarkdown}>
										<Download />
									</Button>
								)}
							</div>
						)}
						{messageText && (isUser || !isRunning) && validMessageTime && (
							<time
								className="ml-1 tabular-nums text-muted-foreground"
								dateTime={validMessageTime.toISOString()}
								title={`${isUser ? '发送于' : '完成于'} ${validMessageTime.toLocaleString('zh-CN')}`}
							>
								{new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(validMessageTime)}
							</time>
						)}
					</MessageFooter>
				)}
			</MessageContent>
		</Message>
	);
}

/**
 * A thinking block with a live-ticking "thinking for Xs" header. Kept as its
 * own component so only thinking blocks pay for the per-second timer.
 */
function ThinkingBlockView({ block }: { block: ThinkingBlock }) {
	const { t } = useTranslation();
	const isRunning = !block.finished_at;

	// Tick once per second while running so the elapsed time updates live.
	const [now, setNow] = useState(() => Date.now());
	useEffect(() => {
		if (!isRunning) return;
		const id = setInterval(() => setNow(Date.now()), 1000);
		return () => clearInterval(id);
	}, [isRunning]);

	const startMs = new Date(block.created_at).getTime();
	const endMs = isRunning ? now : new Date(block.finished_at!).getTime();
	const elapsedSeconds = Math.max(0, (endMs - startMs) / 1000);
	const elapsedText = formatTime(elapsedSeconds);
	return (
		<Collapsible>
			<CollapsibleTrigger asChild>
				<div
					className={cn(
						'group w-full flex items-center gap-2 text-left text-sm text-muted-foreground cursor-pointer',
						isRunning && 'shimmer',
					)}
				>
					<span>
						{t(
							elapsedText === '0s'
								? 'messageBubble.thinking'
								: 'messageBubble.thinkingFor',
							{ duration: elapsedText },
						)}
					</span>
					<ChevronRight className="hidden group-hover:flex group-data-[state=open]:flex size-3 shrink-0 transition-transform group-data-[state=open]:rotate-90" />
				</div>
			</CollapsibleTrigger>
			<CollapsibleContent asChild>
				<Markdown
					animated
					isAnimating={isRunning}
					className="text-muted-foreground bg-muted p-2 rounded text-sm"
				>
					{block.thinking}
				</Markdown>
			</CollapsibleContent>
		</Collapsible>
	);
}

interface ASBlockProps {
	block: ExtendedContentBlock;
}

export function ASBlock({ block, ...props }: ASBlockProps) {
	const { t } = useTranslation();

	switch (block.type) {
		case 'text':
			return (
				<Markdown animated isAnimating={!block.finished_at} {...props}>
					{block.text}
				</Markdown>
			);
		case 'data': {
			const dataType = block.source.media_type.split('/')[0];
			if (dataType === 'audio') return null;
			const data =
				block.source.type === 'url'
					? block.source.url
					: `data:${block.source.media_type};base64,${block.source.data}`;
			switch (dataType) {
				case 'image':
					return (
						<Attachment>
							<AttachmentMedia variant={'image'}>
								<img src={data} alt={block.name || 'Uploaded image'} />
							</AttachmentMedia>
							<AttachmentContent>
								<AttachmentTitle>{block.name}</AttachmentTitle>
								<AttachmentDescription>
									{(
										mime.extension(block.source.media_type) || 'bin'
									).toUpperCase()}
								</AttachmentDescription>
							</AttachmentContent>
						</Attachment>
					);
				case 'video':
					return (
						<Attachment>
							<AttachmentMedia variant={'icon'}>
								<FileVideo2 />
							</AttachmentMedia>
							<AttachmentContent>
								<AttachmentTitle>{block.name}</AttachmentTitle>
								<AttachmentDescription>
									{(
										mime.extension(block.source.media_type) || 'bin'
									).toUpperCase()}
								</AttachmentDescription>
							</AttachmentContent>
						</Attachment>
					);
				default:
					// Unknown files
					return (
						<Attachment>
							<AttachmentMedia variant={'icon'}>
								<FileText />
							</AttachmentMedia>
							<AttachmentContent>
								<AttachmentTitle>{block.name}</AttachmentTitle>
								<AttachmentDescription>
									{(
										mime.extension(block.source.media_type) || 'bin'
									).toUpperCase()}
								</AttachmentDescription>
							</AttachmentContent>
						</Attachment>
					);
			}
		}
		case 'thinking':
			return <ThinkingBlockView block={block} />;
		case 'hint': {
			// Parse source: try JSON, fall back to plain string, default to t('common.message').
			let hintLabel: string;
			let hintSublabel: string | null = null;

			if (block.source) {
				try {
					const parsed = JSON.parse(block.source) as {
						label?: string;
						sublabel?: string;
					};
					hintLabel = parsed.label
						? t(`messageBubble.hintSource.${parsed.label.toLowerCase()}`)
						: block.source;
					hintSublabel = parsed.sublabel ?? null;
				} catch {
					hintLabel = block.source;
				}
			} else {
				hintLabel = t('common.message');
			}
			const items: (TextBlock | DataBlock)[] =
				typeof block.hint === 'string'
					? [
							{
								type: 'text',
								id: `${block.id}-text`,
								text: block.hint,
								created_at: block.created_at,
							},
						]
					: block.hint;
			return (
				<Collapsible>
					<CollapsibleTrigger asChild>
						<div
							className={cn(
								'group w-full flex gap-2 items-center text-sm text-muted-foreground cursor-pointer hover:text-primary',
								!block.finished_at && 'shimmer',
							)}
						>
							<span>{hintLabel + (hintSublabel ? ` - ${hintSublabel}` : '')}</span>
							<ChevronRight className="size-3 shrink-0 transition-transform group-data-[state=open]:rotate-90" />
						</div>
					</CollapsibleTrigger>
					<CollapsibleContent className="bg-muted p-2 rounded text-sm">
						{items.map((item, index) => (
							<ASBlock block={item} key={index} />
						))}
					</CollapsibleContent>
				</Collapsible>
			);
		}
		case 'tool_call_group': {
			const { title, insertions, deletions } = summarizeToolGroup(block.calls, t);
			const allFinished = block.calls.some((c) => !c.result || c.result.state === 'running');
			return (
				<Collapsible defaultOpen={false}>
					<CollapsibleTrigger asChild>
						<div
							className={cn(
								'group w-full flex gap-2 items-center text-sm text-muted-foreground cursor-pointer hover:text-primary',
								allFinished && 'shimmer',
							)}
						>
							<span>{title}</span>
							<ChevronRight className="size-3 shrink-0 transition-transform group-data-[state=open]:rotate-90" />
							<DiffStats insertions={insertions} deletions={deletions} />
						</div>
					</CollapsibleTrigger>
					<CollapsibleContent className="flex flex-col w-full gap-y-1 bg-muted p-2 rounded text-sm text-muted-foreground">
						{block.calls.map((pair) => renderToolCall(pair, t))}
					</CollapsibleContent>
				</Collapsible>
			);
		}

		default:
			return null;
	}
}
