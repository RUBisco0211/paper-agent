import { CheckCircle, XCircle } from 'lucide-react';

import { Badge } from '@upstream/components/ui/badge';
import { Spinner } from '@upstream/components/ui/spinner';
import { useTranslation } from '@upstream/i18n/useI18n';

/**
 * Displays a status badge with icon and label based on execution status.
 * @param root0 - Component props.
 * @param root0.className - Optional CSS class.
 * @param root0.status - The execution status to display.
 * @returns A styled Badge component.
 */
export function StatusBadge({
	className,
	status,
}: {
	className?: string;
	status: 'running' | 'completed' | 'failed';
}) {
	const { t } = useTranslation();
	switch (status) {
		case 'running':
			return (
				<Badge variant="secondary" className={className}>
					<Spinner data-icon="inline-start" />
					{t('common.running')}
				</Badge>
			);
		case 'completed':
			return (
				<Badge variant="success" className={className}>
					<CheckCircle />
					{t('common.completed')}
				</Badge>
			);
		case 'failed':
			return (
				<Badge variant="destructive">
					<XCircle />
					{t('common.failed')}
				</Badge>
			);
	}
}
