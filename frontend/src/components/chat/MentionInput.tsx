import Document from '@tiptap/extension-document';
import HardBreak from '@tiptap/extension-hard-break';
import Mention from '@tiptap/extension-mention';
import Paragraph from '@tiptap/extension-paragraph';
import Placeholder from '@tiptap/extension-placeholder';
import Text from '@tiptap/extension-text';
import { UndoRedo } from '@tiptap/extensions';
import { EditorContent, useEditor, type Editor } from '@tiptap/react';
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';

import { mentionLabel, type MentionCandidate } from '@/lib/mentions';

/** Chip width, gap to the caret and the room needed above it before flipping. */
const PANEL_WIDTH = 288;
const PANEL_GAP = 4;
const PANEL_MIN_SPACE = 240;
const MAX_CANDIDATES = 6;

interface PanelState {
	items: MentionCandidate[];
	index: number;
	left: number;
	/** Distance from the host's bottom edge, used when the panel opens upwards. */
	bottom?: number;
	top?: number;
}

/** What ``suggestion.render`` hands back; typed structurally to avoid the extra dependency. */
interface SuggestionSnapshot {
	items: MentionCandidate[];
	clientRect?: (() => DOMRect | null) | null;
	command: (props: { id: string; label: string }) => void;
}

export interface MentionInputValue {
	/** Plain text of the document, chips read as `@标题`. */
	text: string;
	/** Mentions in document order. */
	mentions: MentionCandidate[];
}

export interface MentionInputRef {
	focus: () => void;
	clear: () => void;
	/** Current text and mentions, read straight off the document. */
	read: () => MentionInputValue;
	/** The editor behind the input, for callers that move the caret themselves. */
	editor: () => Editor | null;
}

interface MentionInputProps {
	/** Papers the current scope can mention; the picker only offers these. */
	candidates: MentionCandidate[];
	placeholder: string;
	disabled?: boolean;
	autoFocus?: boolean;
	/** Text the Tab key completes with while no picker is open. */
	suggestion?: string;
	onChange: (value: MentionInputValue) => void;
	onSubmit: () => void;
	onFocus?: () => void;
	onBlur?: () => void;
}

/**
 * Read the document as plain text, handing each mention to ``renderMention``.
 *
 * Top-level blocks are joined with ``\n`` so a pasted multi-paragraph message
 * keeps its line breaks instead of collapsing into one line.
 *
 * @param editor - The editor to read.
 * @param renderMention - How a chip shows up in the text.
 */
function readDocument(
	editor: Editor,
	renderMention: (mention: MentionCandidate, index: number) => string,
): MentionInputValue {
	const mentions: MentionCandidate[] = [];
	const blocks: string[] = [];
	editor.state.doc.forEach((block) => {
		const parts: string[] = [];
		block.forEach((node) => {
			if (node.type.name === 'mention') {
				const mention = {
					user_paper_id: String(node.attrs.id ?? ''),
					title: String(node.attrs.label ?? ''),
				};
				mentions.push(mention);
				parts.push(renderMention(mention, mentions.length));
			} else if (node.isText) {
				parts.push(node.text ?? '');
			} else if (node.type.name === 'hardBreak') {
				parts.push('\n');
			}
		});
		blocks.push(parts.join(''));
	});
	return { text: blocks.join('\n'), mentions };
}

/**
 * Rich-text composer layer: plain text plus inline, atomically deletable
 * `@文献` chips.
 *
 * The picker is positioned from the suggestion plugin's ``clientRect``, so no
 * floating-ui dependency is needed. While an IME composition is running the
 * picker stays closed and Enter belongs to the IME, not to the message.
 */
export const MentionInput = forwardRef<MentionInputRef, MentionInputProps>(
	(
		{
			candidates,
			placeholder,
			disabled = false,
			autoFocus = false,
			suggestion,
			onChange,
			onSubmit,
			onFocus,
			onBlur,
		},
		ref,
	) => {
		const hostRef = useRef<HTMLDivElement>(null);
		const commandRef = useRef<SuggestionSnapshot['command'] | null>(null);
		const [panel, setPanel] = useState<PanelState | null>(null);
		const panelRef = useRef<PanelState | null>(null);
		// Callbacks and props the editor closes over once, read live on every key.
		const latest = useRef({ candidates, suggestion, onChange, onSubmit, onFocus, onBlur });
		useEffect(() => {
			latest.current = { candidates, suggestion, onChange, onSubmit, onFocus, onBlur };
		});

		const showPanel = useCallback((next: PanelState | null) => {
			panelRef.current = next;
			setPanel(next);
		}, []);

		const placePanel = useCallback(
			(rect: DOMRect | null): Pick<PanelState, 'left' | 'top' | 'bottom'> => {
				const host = hostRef.current;
				if (!host) return { left: 0, top: PANEL_GAP };
				const box = host.getBoundingClientRect();
				const caret = rect ?? box;
				const left = Math.max(0, Math.min(caret.left - box.left, box.width - PANEL_WIDTH));
				if (caret.top > PANEL_MIN_SPACE) {
					return { left, bottom: box.bottom - caret.top + PANEL_GAP };
				}
				return { left, top: caret.bottom - box.top + PANEL_GAP };
			},
			[],
		);

		const syncPanel = useCallback(
			(snapshot: SuggestionSnapshot, preferred: number) => {
				const items = snapshot.items.slice(0, MAX_CANDIDATES);
				if (items.length === 0) {
					showPanel(null);
					return;
				}
				commandRef.current = snapshot.command;
				showPanel({
					items,
					index: preferred < items.length ? preferred : 0,
					...placePanel(snapshot.clientRect?.() ?? null),
				});
			},
			[placePanel, showPanel],
		);

		const movePanel = useCallback(
			(delta: number) => {
				const current = panelRef.current;
				if (!current) return;
				const index = (current.index + delta + current.items.length) % current.items.length;
				showPanel({ ...current, index });
			},
			[showPanel],
		);

		const choose = useCallback(
			(index: number) => {
				const candidate = panelRef.current?.items[index];
				if (!candidate) return;
				showPanel(null);
				commandRef.current?.({ id: candidate.user_paper_id, label: candidate.title });
			},
			[showPanel],
		);

		const editor = useEditor({
			extensions: [
				Document,
				Paragraph,
				Text,
				HardBreak,
				UndoRedo,
				Placeholder.configure({ placeholder }),
				Mention.configure({
					deleteTriggerWithBackspace: true,
					renderHTML: ({ node }) => [
						'span',
						{
							class: 'composer-mention',
							'data-type': 'mention',
							'data-id': String(node.attrs.id ?? ''),
							contenteditable: 'false',
							title: String(node.attrs.label ?? ''),
						},
						`@${mentionLabel(String(node.attrs.label ?? ''))}`,
					],
					suggestion: {
						char: '@',
						// 输入法组词期间不判定 @，也不在组词中提交候选。
						shouldShow: ({ editor: current }) => !current.view.composing,
						items: ({ query }) => {
							const needle = query.trim().toLowerCase();
							return latest.current.candidates
								.filter((candidate) => candidate.title.toLowerCase().includes(needle))
								.slice(0, MAX_CANDIDATES);
						},
						render: () => ({
							onStart: (snapshot) => syncPanel(snapshot, 0),
							onUpdate: (snapshot) => syncPanel(snapshot, panelRef.current?.index ?? 0),
							onExit: () => showPanel(null),
						}),
					},
				}),
			],
			content: '',
			autofocus: autoFocus ? 'end' : false,
			editorProps: {
				attributes: {
					class: 'block w-full outline-none',
					'data-slot': 'composer-editor',
					role: 'textbox',
					'aria-multiline': 'true',
					'aria-label': placeholder,
				},
				handleKeyDown: (view, event) => {
					if (event.isComposing || view.composing) return false;
					const current = panelRef.current;
					if (current && current.items.length > 0) {
						if (event.key === 'ArrowDown') {
							event.preventDefault();
							movePanel(1);
							return true;
						}
						if (event.key === 'ArrowUp') {
							event.preventDefault();
							movePanel(-1);
							return true;
						}
						if (event.key === 'Enter' || event.key === 'Tab') {
							event.preventDefault();
							choose(current.index);
							return true;
						}
						if (event.key === 'Escape') {
							event.preventDefault();
							showPanel(null);
							return true;
						}
					}
					if (event.key === 'Tab' && latest.current.suggestion) {
						event.preventDefault();
						// Insert through the view handed to this handler: under StrictMode
						// the editor instance is replaced, so a captured one may be dead.
						view.dispatch(view.state.tr.insertText(latest.current.suggestion));
						return true;
					}
					if (event.key === 'Enter' && !event.shiftKey) {
						event.preventDefault();
						latest.current.onSubmit();
						return true;
					}
					return false;
				},
			},
			onCreate: ({ editor: created }) => {
				created.setEditable(!disabled);
			},
			onDestroy: () => {
				showPanel(null);
			},
			onUpdate: ({ editor: current }) => {
				// The mirrored string drives the measure layer, so it carries the
				// shortened chip label the reader actually sees; sending reads the
				// document itself and keeps the full title.
				latest.current.onChange(
					readDocument(current, (mention) => `@${mentionLabel(mention.title)}`),
				);
			},
			onFocus: () => latest.current.onFocus?.(),
			onBlur: () => {
				showPanel(null);
				latest.current.onBlur?.();
			},
		});

		useEffect(() => {
			editor?.setEditable(!disabled);
		}, [editor, disabled]);

		useImperativeHandle(
			ref,
			() => ({
				focus: () => editor?.commands.focus(),
				clear: () => {
					showPanel(null);
					editor?.commands.clearContent(true);
				},
				read: () =>
					editor
						? readDocument(editor, (mention) => `@${mention.title}`)
						: { text: '', mentions: [] },
				editor: () => editor ?? null,
			}),
			[editor, showPanel],
		);

		return (
			<div ref={hostRef} className="relative w-full">
				<EditorContent editor={editor} />
				{panel && panel.items.length > 0 && (
					<div
						data-slot="composer-mentions"
						role="listbox"
						aria-label="文献候选"
						className="floating-surface absolute z-50 overflow-hidden"
						style={{
							width: PANEL_WIDTH,
							left: panel.left,
							...(panel.bottom === undefined ? { top: panel.top } : { bottom: panel.bottom }),
						}}
					>
						{panel.items.map((candidate, index) => (
							<button
								key={`${candidate.user_paper_id}-${index}`}
								type="button"
								role="option"
								aria-selected={index === panel.index}
								onMouseDown={(event) => {
									event.preventDefault();
									choose(index);
								}}
								onMouseEnter={() => showPanel({ ...panel, index })}
								className={
									index === panel.index
										? 'block w-full truncate bg-accent px-3 py-1.5 text-left text-sm text-accent-foreground'
										: 'block w-full truncate px-3 py-1.5 text-left text-sm hover:bg-accent/60'
								}
							>
								{candidate.title}
							</button>
						))}
					</div>
				)}
			</div>
		);
	},
);

MentionInput.displayName = 'MentionInput';
