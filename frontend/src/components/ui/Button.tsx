import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Slot } from 'radix-ui';

import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/Tooltip';

const buttonVariants = cva(
	"group/button inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent bg-clip-padding text-ui font-medium whitespace-nowrap transition-all duration-(--motion-duration-hover) ease-(--motion-ease-standard) outline-none select-none focus-visible:border-ring focus-visible:ring-(length:--focus-ring-width) focus-visible:ring-(--focus-ring-color) active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-(--disabled-opacity) aria-invalid:border-destructive aria-invalid:ring-(length:--focus-ring-width) aria-invalid:ring-(--destructive-ring) [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-(--icon-size-md)",
	{
		variants: {
			variant: {
				default: 'bg-primary text-primary-foreground [a]:hover:bg-(--control-primary-hover-bg)',
				outline:
					'border-(--control-outline-border) bg-(--control-outline-bg) hover:bg-(--control-outline-hover-bg) hover:text-foreground aria-expanded:bg-(--control-outline-hover-bg) aria-expanded:text-foreground',
				secondary:
					'bg-secondary text-secondary-foreground hover:bg-(--control-secondary-hover-bg) aria-expanded:bg-secondary aria-expanded:text-secondary-foreground',
				ghost: 'hover:bg-(--control-ghost-hover-bg) hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground',
				destructive:
					'bg-(--destructive-subtle) text-destructive hover:bg-(--destructive-hover) focus-visible:border-(--destructive-border) focus-visible:ring-(--destructive-ring)',
				link: 'text-primary underline-offset-4 hover:underline',
			},
			size: {
				default:
					'h-(--control-height-md) gap-(--control-gap-md) px-(--button-padding-md) has-data-[icon=inline-end]:pr-(--button-padding-xs) has-data-[icon=inline-start]:pl-(--button-padding-xs)',
				xs: "h-(--control-height-xs) gap-(--control-gap-sm) rounded-md px-(--button-padding-xs) text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-(--control-gap-md) has-data-[icon=inline-start]:pl-(--control-gap-md) [&_svg:not([class*='size-'])]:size-(--icon-size-xs)",
				sm: "h-(--control-height-sm) gap-(--control-gap-sm) rounded-md px-(--button-padding-sm) text-ui in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-(--control-gap-md) has-data-[icon=inline-start]:pl-(--control-gap-md) [&_svg:not([class*='size-'])]:size-(--icon-size-sm)",
				lg: 'h-(--control-height-lg) gap-(--control-gap-md) px-(--button-padding-lg) has-data-[icon=inline-end]:pr-(--button-padding-xs) has-data-[icon=inline-start]:pl-(--button-padding-xs)',
				icon: 'size-(--control-height-md)',
				'icon-xs':
					"size-(--control-height-xs) rounded-md in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-(--icon-size-xs)",
				'icon-sm':
					"size-(--control-height-sm) rounded-md in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-(--icon-size-sm)",
				'icon-lg': 'size-(--control-height-lg)',
			},
		},
		defaultVariants: {
			variant: 'default',
			size: 'default',
		},
	},
);

function Button({
	className,
	variant = 'default',
	size = 'default',
	asChild = false,
	tooltip = undefined,
	...props
}: React.ComponentProps<'button'> &
	VariantProps<typeof buttonVariants> & {
		asChild?: boolean;
		tooltip?: string;
	}) {
	const Comp = asChild ? Slot.Root : 'button';

	if (tooltip === undefined) {
		return (
			<Comp
				data-slot="button"
				data-variant={variant}
				data-size={size}
				className={cn(buttonVariants({ variant, size, className }))}
				{...props}
			/>
		);
	}

	return (
		<Tooltip>
			<TooltipTrigger asChild>
				<Comp
					data-slot="button"
					data-variant={variant}
					data-size={size}
					className={cn(buttonVariants({ variant, size, className }))}
					{...props}
				/>
			</TooltipTrigger>
			<TooltipContent>{tooltip}</TooltipContent>
		</Tooltip>
	);
}

export { Button, buttonVariants };
