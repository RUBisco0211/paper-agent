import type { ChannelTypeSchema } from '@upstream/api';
import { Avatar, AvatarFallback, AvatarImage } from '@upstream/components/ui/avatar';
import { avatarTint } from '@upstream/utils/common';

/** Brand avatar for a channel type; falls back to a tinted initial. */
export function TypeAvatar({ type, className }: { type?: ChannelTypeSchema; className?: string }) {
	const seed = type?.channel_type ?? '';
	const label = type?.display_name ?? seed;
	return (
		<Avatar className={className}>
			<AvatarImage src={type?.icon_url || undefined} alt={label} />
			<AvatarFallback className="rounded-[inherit]" style={avatarTint(seed)}>
				{label.slice(0, 1).toUpperCase()}
			</AvatarFallback>
		</Avatar>
	);
}
