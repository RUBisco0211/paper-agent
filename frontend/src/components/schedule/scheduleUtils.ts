import type { ParsedSchedule } from "@/types/schedule"

export function parseCronExpression(cronExpression: string, startedAt: string): ParsedSchedule {
	const parts = cronExpression.trim().split(/\s+/);
	if (parts.length !== 5) {
		return { frequency: 'custom', time: '00:00' };
	}

	const [minute, hour, day, month, weekday] = parts;
	const time = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`;

	if (day === '*' && month === '*' && weekday === '*') {
		return { frequency: 'daily', time };
	}

	if (day === '*' && month === '*' && weekday !== '*') {
		return { frequency: 'weekly', time, weekday: parseInt(weekday) };
	}

	if (day !== '*' && month === '*' && weekday === '*') {
		return { frequency: 'monthly', time, dayOfMonth: parseInt(day) };
	}

	if (day !== '*' && month !== '*') {
		return { frequency: 'once', time, date: new Date(startedAt) };
	}

	return { frequency: 'custom', time };
}

export function getFrequencyLabel(parsed: ParsedSchedule, t: (key: string) => string): string {
	switch (parsed.frequency) {
		case 'daily':
			return t('schedule.freqDaily');
		case 'weekly':
			return t('schedule.freqWeekly');
		case 'monthly':
			return t('schedule.freqMonthly');
		case 'once':
			return t('schedule.freqOnce');
		default:
			return 'Custom';
	}
}
