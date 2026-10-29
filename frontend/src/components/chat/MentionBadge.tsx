import type { ReactNode } from 'react';
import { HoverCard as HoverCardPrimitive } from 'radix-ui';

import { Badge } from '@/components/ui/Badge';

/**
 * An @-mentioned paper inside a rendered message.
 *
 * Shares the reference badge's chrome so both read as the same family: outline
 * chip in the quote accent colour, title truncated, full name on hover.
 *
 * @param root0 - The chip props.
 * @param root0.label - What the chip shows, already shortened.
 * @param root0.title - The full paper title behind the chip.
 */
export function MentionBadge({ label, title }: { label: ReactNode; title: string }) {
	return (
		<Badge
			variant="outline"
			className="max-w-64 gap-0 border-(--message-quote-accent) px-1 font-normal"
		>
			<HoverCardPrimitive.Root openDelay={250} closeDelay={120}>
				<HoverCardPrimitive.Trigger asChild>
					<span tabIndex={0} className="max-w-52 truncate px-1 py-0.5">
						{label}
					</span>
				</HoverCardPrimitive.Trigger>
				<HoverCardPrimitive.Portal>
					<HoverCardPrimitive.Content
						side="top"
						align="start"
						sideOffset={8}
						className="floating-surface z-50 flex w-(--quote-preview-width) max-w-[calc(100vw-2rem)] flex-col gap-2 p-(--quote-preview-padding) text-sm outline-hidden data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0"
					>
						<p className="text-xs font-medium text-muted-foreground">提及文献</p>
						<p className="whitespace-pre-wrap wrap-break-word">{title}</p>
					</HoverCardPrimitive.Content>
				</HoverCardPrimitive.Portal>
			</HoverCardPrimitive.Root>
		</Badge>
	);
}
