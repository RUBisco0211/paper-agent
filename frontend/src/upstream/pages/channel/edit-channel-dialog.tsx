import { CircleAlert, Loader2, Save, X } from 'lucide-react';
import * as React from 'react';

import type { ChannelRecord, ChannelTypeSchema } from '@upstream/api';
import { channelApi } from '@upstream/api';
import { Alert, AlertDescription } from '@upstream/components/ui/alert';
import { Button } from '@upstream/components/ui/button';
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from '@upstream/components/ui/dialog';
import { useAgents } from '@upstream/hooks/useAgents';
import { useTranslation } from '@upstream/i18n/useI18n';
import {
	ChannelForm,
	channelFormFromRecord,
	defaultChannelForm,
	isChannelFormValid,
	toUpdateRequest,
} from '@upstream/pages/channel/channel-form';

interface Props {
	channel: ChannelRecord | null;
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onUpdated?: () => void;
}

export function EditChannelDialog({ channel, open, onOpenChange, onUpdated }: Props) {
	const { t } = useTranslation();
	const { agents } = useAgents();
	const [form, setForm] = React.useState(defaultChannelForm);
	const [channelTypes, setChannelTypes] = React.useState<ChannelTypeSchema[]>([]);
	const [loading, setLoading] = React.useState(false);
	const [error, setError] = React.useState('');

	React.useEffect(() => {
		if (open && channel) {
			setForm(channelFormFromRecord(channel));
			setError('');
			channelApi
				.listTypes()
				.then(setChannelTypes)
				.catch(() => {});
		}
	}, [open, channel]);

	const valid = isChannelFormValid(form, 'edit');

	const handleSubmit = async () => {
		if (!channel || !valid) return;
		setError('');
		setLoading(true);
		try {
			await channelApi.update(channel.id, toUpdateRequest(form));
			onUpdated?.();
			onOpenChange(false);
		} catch (e) {
			setError(e instanceof Error ? e.message : String(e));
		} finally {
			setLoading(false);
		}
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="!w-[560px] !max-w-[560px]">
				<DialogHeader>
					<DialogTitle>{t('channel.edit.title')}</DialogTitle>
					<DialogDescription>{t('channel.edit.description')}</DialogDescription>
				</DialogHeader>

				<div className="no-scrollbar -mx-4 max-h-[75vh] overflow-y-auto px-4 pt-1">
					<ChannelForm
						mode="edit"
						value={form}
						onChange={setForm}
						agents={agents}
						channelTypes={channelTypes}
					/>
					{error && (
						<Alert variant="destructive" className="mt-2">
							<CircleAlert />
							<AlertDescription>{error}</AlertDescription>
						</Alert>
					)}
				</div>

				<DialogFooter>
					<Button variant="ghost" onClick={() => onOpenChange(false)} disabled={loading}>
						<X className="size-3.5" />
						{t('common.cancel')}
					</Button>
					<Button onClick={handleSubmit} disabled={loading || !valid}>
						{loading ? (
							<Loader2 className="size-3.5 animate-spin" />
						) : (
							<Save className="size-3.5" />
						)}
						{t('common.save')}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
