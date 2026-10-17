import * as React from 'react';
import { Label as LabelPrimitive } from 'radix-ui';

import { cn } from '@upstream/lib/utils';

function Label({ className, ...props }: React.ComponentProps<typeof LabelPrimitive.Root>) {
	return (
		<LabelPrimitive.Root
			data-slot="label"
			className={cn(
				'flex items-center gap-(--control-gap-lg) text-label leading-none font-normal text-muted-foreground uppercase tracking-label select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-(--disabled-opacity) peer-disabled:cursor-not-allowed peer-disabled:opacity-(--disabled-opacity)',
				className,
			)}
			{...props}
		/>
	);
}

export { Label };
