import * as React from 'react';
import { Switch as SwitchPrimitive } from 'radix-ui';

import { cn } from '@/lib/utils';

/*
 * 取值全部来自 index.css 的 --switch-* 语义变量：轨道两个尺寸、滑块大小
 * 与两种状态的配色都由主题集中维护，这里只描述状态。
 *
 * 两种状态的样式直接由 checked 决定，不依赖库写在节点上的 data-state：
 * 轨道底色和滑块位移都按当前值给出，受控与非受控表现一致。
 */
function Switch({
	className,
	size = 'default',
	checked,
	defaultChecked,
	onCheckedChange,
	...props
}: React.ComponentProps<typeof SwitchPrimitive.Root> & {
	size?: 'sm' | 'default';
}) {
	const compact = size === 'sm';
	const [uncontrolled, setUncontrolled] = React.useState(defaultChecked ?? false);
	const isOn = checked ?? uncontrolled;
	return (
		<SwitchPrimitive.Root
			data-slot="switch"
			data-size={size}
			checked={checked}
			defaultChecked={defaultChecked}
			onCheckedChange={(next) => {
				if (checked === undefined) setUncontrolled(next);
				onCheckedChange?.(next);
			}}
			style={{
				height: compact
					? 'var(--switch-height-sm)'
					: 'var(--switch-height-default)',
				width: compact
					? 'var(--switch-width-sm)'
					: 'var(--switch-width-default)',
				// 底色直接写在这层，避免工具类与该组件里其它背景声明互相覆盖。
				backgroundColor: isOn
					? 'var(--switch-track-checked)'
					: 'var(--switch-track-unchecked)',
			}}
			className={cn(
				'peer group/switch relative inline-flex shrink-0 items-center rounded-full border border-transparent transition-all outline-none',
				'after:absolute after:-inset-x-3 after:-inset-y-2',
				'focus-visible:border-(--switch-track-checked) focus-visible:ring-3 focus-visible:ring-(--focus-ring-color)',
				'aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-(--destructive-ring)',
				'disabled:cursor-not-allowed disabled:opacity-50',
				className,
			)}
			{...props}
		>
			<SwitchPrimitive.Thumb
				data-slot="switch-thumb"
				className={cn(
					'pointer-events-none block rounded-full ring-0 shadow-sm transition-transform',
					'bg-(--switch-thumb)',
					isOn && 'dark:bg-(--switch-thumb-checked)',
					compact
						? 'size-(--switch-thumb-size-sm)'
						: 'size-(--switch-thumb-size-default)',
				)}
				style={{
					translate: isOn
						? compact
							? 'calc(var(--switch-width-sm) - var(--switch-thumb-size-sm) - var(--switch-thumb-inset))'
							: 'calc(var(--switch-width-default) - var(--switch-thumb-size-default) - var(--switch-thumb-inset))'
						: 'var(--switch-thumb-inset)',
				}}
			/>
		</SwitchPrimitive.Root>
	);
}

export { Switch };
