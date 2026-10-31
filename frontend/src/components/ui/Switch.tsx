import * as React from 'react';
import { Switch as SwitchPrimitive } from 'radix-ui';

import { cn } from '@/lib/utils';

/*
 * 取值全部来自 index.css 的 --switch-* 语义变量：轨道两个尺寸、滑块大小
 * 与两种状态的配色都由主题集中维护，这里只描述状态。
 */
function Switch({
	className,
	size = 'default',
	...props
}: React.ComponentProps<typeof SwitchPrimitive.Root> & {
	size?: 'sm' | 'default';
}) {
	const compact = size === 'sm';
	return (
		<SwitchPrimitive.Root
			data-slot="switch"
			data-size={size}
			style={{
				height: compact
					? 'var(--switch-height-sm)'
					: 'var(--switch-height-default)',
				width: compact
					? 'var(--switch-width-sm)'
					: 'var(--switch-width-default)',
			}}
			className={cn(
				'peer group/switch relative inline-flex shrink-0 items-center rounded-full border border-transparent transition-all outline-none',
				'after:absolute after:-inset-x-3 after:-inset-y-2',
				'focus-visible:border-(--switch-track-checked) focus-visible:ring-3 focus-visible:ring-(--focus-ring-color)',
				'aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-(--destructive-ring)',
				'data-unchecked:bg-(--switch-track-unchecked) data-checked:bg-(--switch-track-checked)',
				'disabled:cursor-not-allowed disabled:opacity-50',
				className,
			)}
			{...props}
		>
			<SwitchPrimitive.Thumb
				data-slot="switch-thumb"
				className={cn(
					// 滑块贴左留出 inset；选中时推到轨道右端，位移由轨道宽度与滑块宽度决定。
					'pointer-events-none block rounded-full ring-0 transition-transform',
					'shadow-sm',
					'bg-(--switch-thumb) dark:data-checked:bg-(--switch-thumb-checked)',
					size === 'sm'
						? 'size-(--switch-thumb-size-sm)'
						: 'size-(--switch-thumb-size-default)',
					'data-unchecked:translate-x-(--switch-thumb-inset)',
					'data-checked:data-[size=default]:translate-x-[calc(var(--switch-width-default)-var(--switch-thumb-size-default)-var(--switch-thumb-inset))]',
					'data-checked:data-[size=sm]:translate-x-[calc(var(--switch-width-sm)-var(--switch-thumb-size-sm)-var(--switch-thumb-inset))]',
				)}
			/>
		</SwitchPrimitive.Root>
	);
}

export { Switch };
