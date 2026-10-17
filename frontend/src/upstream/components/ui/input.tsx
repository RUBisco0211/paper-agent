import * as React from 'react';

import { cn } from '@upstream/lib/utils';

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
	return (
		<input
			type={type}
			data-slot="input"
			className={cn(
				'h-(--control-height-md) w-full min-w-0 rounded-lg border border-input bg-(--control-input-bg) px-(--button-padding-md) py-1 text-base transition-colors duration-(--motion-duration-hover) ease-(--motion-ease-standard) outline-none file:inline-flex file:h-(--control-height-xs) file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-(length:--focus-ring-width) focus-visible:ring-(--focus-ring-color) disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-(--control-disabled-bg) disabled:opacity-(--disabled-opacity) aria-invalid:border-destructive aria-invalid:ring-(length:--focus-ring-width) aria-invalid:ring-(--destructive-ring) md:text-sm',
				className,
			)}
			{...props}
		/>
	);
}

export { Input };
