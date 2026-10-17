import * as React from 'react';

import { cn } from '@upstream/lib/utils';

function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
	return (
		<textarea
			data-slot="textarea"
			className={cn(
				'flex field-sizing-content min-h-16 w-full rounded-lg border border-input bg-(--control-input-bg) px-(--button-padding-md) py-2 text-base transition-colors duration-(--motion-duration-hover) ease-(--motion-ease-standard) outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-(length:--focus-ring-width) focus-visible:ring-(--focus-ring-color) disabled:cursor-not-allowed disabled:bg-(--control-disabled-bg) disabled:opacity-(--disabled-opacity) aria-invalid:border-destructive aria-invalid:ring-(length:--focus-ring-width) aria-invalid:ring-(--destructive-ring) md:text-sm',
				className,
			)}
			{...props}
		/>
	);
}

export { Textarea };
