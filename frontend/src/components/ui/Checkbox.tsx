import * as React from 'react';
import { Checkbox as CheckboxPrimitive } from 'radix-ui';

import { cn } from '@/lib/utils';
import { CheckIcon } from 'lucide-react';

/*
 * 取值全部来自 index.css 的 --checkbox-* 语义变量：
 * 尺寸、圆角、描边和选中态都由主题集中维护，这里只描述状态。
 */
function Checkbox({ className, ...props }: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
	return (
		<CheckboxPrimitive.Root
			data-slot="checkbox"
			className={cn(
				'peer relative flex size-(--checkbox-size) shrink-0 items-center justify-center rounded-(--checkbox-radius) border-(length:--checkbox-border-width) border-(--checkbox-border) bg-(--checkbox-background) text-current transition-colors outline-none',
				// 选中态的填充不能被 hover 覆盖：:where() 权重更低，这里只在未选中时上底色。
				'data-unchecked:hover:bg-(--checkbox-hover-background)',
				'after:absolute after:-inset-x-3 after:-inset-y-2',
				'focus-visible:border-(--checkbox-checked-border) focus-visible:ring-3 focus-visible:ring-(--focus-ring-color)',
				'disabled:cursor-not-allowed disabled:opacity-50 group-has-disabled/field:opacity-50',
				'aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-(--destructive-ring)',
				'data-checked:border-(--checkbox-checked-border) data-checked:bg-(--checkbox-checked-background) data-checked:text-(--checkbox-checked-foreground)',
				className,
			)}
			{...props}
		>
			<CheckboxPrimitive.Indicator
				data-slot="checkbox-indicator"
				className="grid place-content-center text-current transition-none [&>svg]:size-(--checkbox-icon-size)"
			>
				<CheckIcon />
			</CheckboxPrimitive.Indicator>
		</CheckboxPrimitive.Root>
	);
}

export { Checkbox };
