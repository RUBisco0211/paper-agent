import type { ContentBlock, TextBlock } from '@agentscope-ai/agentscope/message';
import {
	Paperclip,
	Loader2,
	Square,
	type LucideIcon,
	XIcon,
	FileText,
	ArrowUp,
} from 'lucide-react';
import mime from 'mime';
import React, {
	useState,
	useRef,
	useMemo,
	useLayoutEffect,
	type KeyboardEvent,
	useImperativeHandle,
	forwardRef,
} from 'react';

import { Button } from '@/components/ui/Button';
import { Kbd } from '@/components/ui/Kbd';
import {
	Attachment,
	AttachmentAction,
	AttachmentActions,
	AttachmentContent,
	AttachmentDescription,
	AttachmentGroup,
	AttachmentMedia,
	AttachmentTitle,
} from '@/components/ui/Attachment';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/Tooltip';
import type { ReplyPhase } from '@/hooks/useMessages';
import { useTranslation } from '@/i18n/useI18n';
import { cn } from '@/lib/utils';

/**
 * Represents a file that has been selected and processed (or is being processed).
 */
interface ProcessedFile {
	/** Original file name for display */
	name: string;
	/** Processing status */
	status: 'processing' | 'done';
	/** The resulting ContentBlock after processing (available when status === 'done') */
	block: ContentBlock | null;
}

interface TextInputProps {
	onSend: (blocks: ContentBlock[]) => void | Promise<boolean>;
	sendDisabled?: boolean;
	placeholder?: string;
	autoComplete?: (input: string) => string | null;
	disabled?: boolean;
	className?: string;
	/**
	 * Controls which file types the file picker accepts.
	 * Uses standard MIME types and file extensions, e.g.:
	 *   - Images:    "image/*" or "image/jpeg", "image/png"
	 *   - Audio:     "audio/*" or "audio/mpeg", "audio/wav"
	 *   - Video:     "video/*"
	 *   - Plain text:"text/plain"
	 *   - PDF:       "application/pdf"
	 *   - Word:      ".doc,.docx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
	 *   - Excel:     ".xls,.xlsx,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
	 *
	 * When undefined → no restriction (all files allowed).
	 * When empty array [] → attachment button is disabled (model accepts no files).
	 */
	allowedInputTypes?: string[];
	/**
	 * Called immediately when a file is selected (at attach time, NOT at send time).
	 * Should resolve to a ContentBlock to include in the message, or null to skip the file.
	 * Runs concurrently for all selected files; the UI shows a loading state per file while processing.
	 */
	fileProcessor: (file: File) => Promise<ContentBlock | null>;
	/**
	 * The current reply lifecycle phase from ``useMessages``. Drives the
	 * send / stop button in one shot:
	 *   - ``idle`` — Send (enabled when there is content to send)
	 *   - ``streaming`` — Stop (click to interrupt)
	 *   - ``interrupting`` — Stop (disabled while the interrupt is in flight)
	 */
	phase?: ReplyPhase;
	onInterrupt?: () => void;
	/**
	 * Content rendered directly above the input pill, inside the outer
	 * wrapper that {@link className} styles (e.g. the working directory
	 * and git status).
	 */
	headerSlot?: React.ReactNode;
	quoteSlot?: React.ReactNode;
	allowEmptyText?: boolean;
}

export interface TextInputRef {
	focus: () => void;
}

/**
 * A text input component with file attachment support and autocomplete functionality.
 *
 * @param root0 - The component props.
 * @param root0.onSend - Callback function to handle sending content blocks.
 * @param root0.placeholder - Placeholder text for the input field.
 * @param root0.autoComplete - Function to provide autocomplete suggestions.
 * @param root0.disabled - Whether the input is disabled.
 * @param root0.className - Additional CSS classes for styling.
 * @returns A TextInput component.
 */
export const TextInput = forwardRef<TextInputRef, TextInputProps>(
	(
		{
			onSend,
			sendDisabled = false,
			placeholder,
			autoComplete,
			disabled = false,
			className,
			allowedInputTypes,
			fileProcessor,
			phase = 'idle',
			onInterrupt,
			headerSlot,
			quoteSlot,
			allowEmptyText = false,
		},
		ref,
	) => {
		const { t } = useTranslation();
		const defaultPlaceholder = placeholder || t('chat.inputPlaceholder');
		const [value, setValue] = useState('');
		const [files, setFiles] = useState<ProcessedFile[]>([]);
		const [isFocused, setIsFocused] = useState(false);
		const textareaRef = useRef<HTMLTextAreaElement>(null);
		const fileInputRef = useRef<HTMLInputElement>(null);
		const measureRef = useRef<HTMLSpanElement>(null);
		/** ``true`` — textarea takes the full width, buttons drop to their own row. */
		const [isStacked, setIsStacked] = useState(false);

		// Derive the accept attribute for the hidden file input
		const acceptAttr =
			allowedInputTypes && allowedInputTypes.length > 0
				? allowedInputTypes.join(',')
				: undefined;

		// Attachment button is disabled when the model explicitly accepts no file types
		const attachDisabled =
			disabled || (allowedInputTypes !== undefined && allowedInputTypes.length === 0);

		// Whether any file is still being processed (block send until all done)
		const hasProcessing = files.some((f) => f.status === 'processing');

		useImperativeHandle(ref, () => ({
			focus: () => textareaRef.current?.focus(),
		}));

		// Grow the textarea with its content. The ``auto`` reset is what lets it
		// shrink again — ``scrollHeight`` never reports less than the current height.
		useLayoutEffect(() => {
			const textarea = textareaRef.current;
			if (!textarea) return;
			textarea.style.height = 'auto';
			textarea.style.height = `${textarea.scrollHeight}px`;
			// Stacking widens the textarea, so the line count has to be redone.
		}, [value, isStacked]);

		// Measured on the ghost, not the textarea: stacking widens the textarea, so
		// measuring it would flip-flop (wraps → stack → fits → unstack → wraps).
		useLayoutEffect(() => {
			const ghost = measureRef.current;
			if (!ghost) return;
			const lineHeight = Number.parseFloat(getComputedStyle(ghost).lineHeight);
			setIsStacked(ghost.scrollHeight > lineHeight);
		}, [value]);

		// Calculate autocomplete suggestion using useMemo
		const suggestion = useMemo(() => {
			if (autoComplete && value && isFocused) {
				const result = autoComplete(value);
				// Only return the part after the cursor
				if (result && result.startsWith(value)) {
					return result.substring(value.length);
				}
				return result || '';
			}
			return '';
		}, [value, autoComplete, isFocused]);

		const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
			// Tab key to select autocomplete
			if (e.key === 'Tab' && suggestion) {
				e.preventDefault();
				setValue(value + suggestion);
				return;
			}

			// Enter to send message, Shift+Enter for new line
			if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
				e.preventDefault();
				handleSend();
			}
		};

		const handleSend = async () => {
			if ((!value.trim() && !allowEmptyText) || disabled || sendDisabled || hasProcessing) return;

			const blocks: ContentBlock[] = [];

			// Add text block
			if (value.trim()) {
				const textBlock: TextBlock = {
					id: crypto.randomUUID(),
					type: 'text',
					text: value.trim(),
					created_at: new Date().toISOString(),
					finished_at: new Date().toISOString(),
				};
				blocks.push(textBlock);
			}

			// Add processed file blocks (skip errored ones)
			files.forEach((f) => {
				if (f.status === 'done' && f.block) {
					blocks.push(f.block);
				}
			});

			const accepted = await onSend(blocks);
			if (accepted === false) return;
			setValue('');
			setFiles([]);
		};

		/**
		 * Send / stop button configuration derived from the current reply
		 * phase. One struct = one branch of rendering, so the JSX stays flat.
		 */
		const sendButton: {
			icon: LucideIcon;
			tooltip: string;
			disabled: boolean;
			onClick: (() => void) | undefined;
		} = (() => {
			if (phase === 'streaming') {
				return {
					icon: Square,
					tooltip: t('textInput.stop'),
					disabled: false,
					onClick: onInterrupt,
				};
			}
			if (phase === 'interrupting') {
				return {
					icon: Square,
					tooltip: t('textInput.stopping'),
					disabled: true,
					onClick: onInterrupt,
				};
			}
			return {
				icon: ArrowUp,
				tooltip: t('textInput.send'),
				disabled: disabled || sendDisabled || (!value.trim() && !allowEmptyText) || hasProcessing,
				onClick: () => { void handleSend(); },
			};
		})();

		const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
			if (!e.target.files) return;
			const selected = Array.from(e.target.files);
			// Reset input value so the same file can be re-selected
			e.target.value = '';

			selected.forEach((file) => {
				// Insert a placeholder in processing state
				const placeholder: ProcessedFile = {
					name: file.name,
					status: 'processing',
					block: null,
				};

				setFiles((prev) => [...prev, placeholder]);

				fileProcessor(file)
					.then((block) => {
						setFiles(
							(prev) =>
								prev
									.map((f) =>
										f.name === file.name && f.status === 'processing'
											? block
												? { ...f, status: 'done', block }
												: null
											: f,
									)
									.filter(Boolean) as ProcessedFile[],
						);
					})
					.catch(() => {
						// Caller is responsible for error notification (e.g. toast).
						// Just silently remove the entry here.
						setFiles((prev) =>
							prev.filter(
								(f) => !(f.name === file.name && f.status === 'processing'),
							),
						);
					});
			});
		};

		return (
			<div data-slot="composer" className={cn('flex flex-col', className)}>
				{headerSlot}
				<div
					id="tour-chat-input"
					data-slot="composer-input-shell"
					className="flex w-full flex-col rounded-lg border bg-background px-2"
					data-tour="chat-input"
				>
					{quoteSlot && <div className="flex flex-wrap gap-1.5 px-2 pt-2">{quoteSlot}</div>}
					{files.length > 0 && (
						<AttachmentGroup className={'w-full max-w-full px-1 mt-1'}>
							{files.map((file, index) => {
								const isImage =
									file.block &&
									file.block.type === 'data' &&
									file.block.source.media_type.startsWith('image/');
								let data: undefined | string;
								if (file.block && file.block.type === 'data') {
									const block = file.block;
									data =
										block.source.type === 'url'
											? block.source.url
											: `data:${block.source.media_type};base64,${block.source.data}`;
								}

								return (
									<Attachment>
										<AttachmentMedia variant={isImage ? 'image' : 'icon'}>
											{file.status === 'processing' ? (
												<Loader2 className="size-3 shrink-0 animate-spin" />
											) : isImage ? (
												<img src={data} alt={file.name} />
											) : (
												<FileText className="size-3" />
											)}
										</AttachmentMedia>
										<AttachmentContent>
											<AttachmentTitle>{file.name}</AttachmentTitle>
											<AttachmentDescription>
												{file.status === 'processing'
													? t('common.uploading')
													: (
															mime.getExtension(
																mime.getType(file.name) || 'bin',
															) || 'bin'
														).toUpperCase()}
											</AttachmentDescription>
										</AttachmentContent>
										<AttachmentActions>
											<AttachmentAction
												onClick={() =>
													setFiles(files.filter((_, i) => i !== index))
												}
											>
												<XIcon />
											</AttachmentAction>
										</AttachmentActions>
									</Attachment>
								);
							})}
						</AttachmentGroup>
					)}

					{/* ``items-end`` in both layouts: the buttons are then already at the
					    bottom before stacking moves them there, so nothing jumps. */}
					<div className="relative flex flex-wrap items-end justify-end">
						{/* Ghost row, always laid out side-by-side, so the width it hands
						    the text is the narrow one whichever layout is on screen. */}
						<div
							aria-hidden
							className="pointer-events-none invisible absolute inset-x-0 top-0 flex h-0 items-start overflow-hidden"
						>
							<div className="min-w-0 flex-1">
								{/* Padding-x and line-height decide where text wraps, so they
								    match the textarea; padding-y is left off on purpose. */}
								<span
									ref={measureRef}
									data-slot="composer-measure"
									className="block"
								>
									{value}
								</span>
							</div>
							{/* Stands in for the button cluster below — keep the count, the
							    gap and the ``size-9`` footprint in step with it. */}
							<div className="flex shrink-0 gap-(--control-gap-lg)">
								<div className="size-(--control-height-lg)" />
								<div className="size-(--control-height-lg)" />
							</div>
						</div>

						{/* ``min-w-0`` lets the textarea shrink instead of pushing the
						    buttons out of the row once the text gets long. */}
						<div
							className={cn('relative min-w-0', isStacked ? 'basis-full' : 'flex-1')}
						>
							{/* ``block`` — inline-block would sit on the text baseline and
							    leave a descender gap that makes the wrapper taller. */}
							<textarea
								ref={textareaRef}
								data-slot="composer-textarea"
								value={value}
								onChange={(e) => setValue(e.target.value)}
								onKeyDown={handleKeyDown}
								onFocus={() => setIsFocused(true)}
								onBlur={() => setIsFocused(false)}
								placeholder={defaultPlaceholder}
								disabled={disabled}
								rows={1}
								className="block w-full resize-none rounded-md border-0 bg-transparent outline-none placeholder:text-muted-foreground focus:outline-none disabled:cursor-not-allowed disabled:opacity-(--disabled-opacity)"
								autoFocus={true}
							/>

							{/* Autocomplete overlay — its padding and line-height mirror the
							    textarea's, or the suggestion drifts off the real text. */}
							{suggestion && isFocused && (
								<div
									data-slot="composer-suggestion"
									className="pointer-events-none absolute left-0 top-0"
								>
									{/* Invisible input text */}
									<span className="invisible">{value}</span>
									{/* Suggestion text */}
									<span className="text-muted-foreground">{suggestion}</span>
									{/* Tab hint */}
									<span className="ml-2 text-xs text-muted-foreground/60">
										<Kbd>Tab</Kbd> {t('textInput.toComplete')}
									</span>
								</div>
							)}
						</div>

						{/* Collapsed-height box centring the buttons, so a single line still
						    reads as centred while the row bottom-aligns them. */}
						<div
							data-slot="composer-actions"
							className="flex shrink-0 items-center gap-(--control-gap-lg)"
						>
							{/* Attachment button */}
							<Tooltip>
								<TooltipTrigger asChild>
									<Button
										type="button"
										variant="ghost"
										size="icon-lg"
										onClick={() => fileInputRef.current?.click()}
										disabled={attachDisabled}
										className="shrink-0 rounded-md"
									>
										<Paperclip />
									</Button>
								</TooltipTrigger>
								<TooltipContent>
									{attachDisabled && allowedInputTypes?.length === 0
										? t('textInput.attachNotSupported')
										: t('textInput.attach')}
								</TooltipContent>
							</Tooltip>

							{/* Send / Stop button — driven by ``sendButton`` config */}
							<Tooltip>
								<TooltipTrigger asChild>
									<Button
										type="button"
										onClick={sendButton.onClick}
										disabled={sendButton.disabled}
										size="icon-lg"
										className="shrink-0 rounded-md"
									>
										<sendButton.icon className="h-4 w-4" />
									</Button>
								</TooltipTrigger>
								<TooltipContent>{sendButton.tooltip}</TooltipContent>
							</Tooltip>

							{/* Hidden file input */}
							<input
								ref={fileInputRef}
								type="file"
								multiple
								accept={acceptAttr}
								onChange={handleFileSelect}
								className="hidden"
							/>
						</div>
					</div>
				</div>
			</div>
		);
	},
);

TextInput.displayName = 'TextInput';
