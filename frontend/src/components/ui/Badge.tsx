import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Slot } from 'radix-ui';

import { cn } from '@/lib/utils';

const badgeVariants = cva(
	'group/badge inline-flex h-(--badge-height) w-fit shrink-0 items-center justify-center gap-(--control-gap-sm) overflow-hidden rounded-md border border-transparent px-2 py-0.5 text-label font-medium uppercase tracking-label whitespace-nowrap transition-all duration-(--motion-duration-hover) ease-(--motion-ease-standard) focus-visible:border-ring focus-visible:ring-(length:--focus-ring-width) focus-visible:ring-(--focus-ring-color) has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-(--destructive-ring) [&>svg]:pointer-events-none [&>svg]:size-(--icon-size-xs)',
	{
		variants: {
			variant: {
				default: 'bg-primary text-primary-foreground [a]:hover:bg-(--control-primary-hover-bg)',
				secondary: 'bg-secondary text-secondary-foreground [a]:hover:bg-(--control-secondary-hover-bg)',
				destructive:
					'border-(--destructive-border) bg-(--destructive-subtle) text-destructive focus-visible:ring-(--destructive-ring) [a]:hover:bg-(--destructive-hover)',
				success: 'border-(--success-border) bg-(--success-subtle) text-success',
				warning: 'border-(--warning-border) bg-(--warning-subtle) text-warning',
				info: 'border-(--info-border) bg-(--info-subtle) text-info',
				outline:
					'border-border text-foreground [a]:hover:bg-(--control-outline-hover-bg) [a]:hover:text-muted-foreground',
				ghost: 'hover:bg-(--control-ghost-hover-bg) hover:text-muted-foreground',
				link: 'text-primary underline-offset-4 hover:underline',
			},
		},
		defaultVariants: {
			variant: 'default',
		},
	},
);

function Badge({
	className,
	variant = 'default',
	asChild = false,
	...props
}: React.ComponentProps<'span'> & VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
	const Comp = asChild ? Slot.Root : 'span';

	return (
		<Comp
			data-slot="badge"
			data-variant={variant}
			className={cn(badgeVariants({ variant }), className)}
			{...props}
		/>
	);
}

export { Badge, badgeVariants };
