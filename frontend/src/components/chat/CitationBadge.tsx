import type { ReactNode } from 'react';

import { useCitationOpen } from '@/components/chat/CitationProvider';

/**
 * An inline `[n]` citation in an answer.
 *
 * The number is the label; the paper, page and snippet are fetched only when
 * the reader asks for them, so a long answer costs no extra requests.
 *
 * @param root0 - The chip props.
 * @param root0.citationId - Registered citation id the marker pointed at.
 * @param root0.children - The `[n]` label the marker was rewritten to.
 */
export function CitationBadge({ citationId, children }: { citationId: string; children?: ReactNode }) {
	const open = useCitationOpen();
	return (
		<button
			type="button"
			onClick={() => open?.(citationId)}
			className="mx-0.5 inline cursor-pointer align-super text-xs font-medium text-primary hover:underline"
		>
			{children}
		</button>
	);
}
