import { CircleAlert, Loader2, PlusCircle } from 'lucide-react';
import { useState, useEffect } from 'react';

import { credentialApi } from '@upstream/api';
import type { CredentialSchema } from '@upstream/api';
import { SchemaForm, type SchemaFormValue } from '@upstream/components/form/SchemaForm';
import { Button } from '@upstream/components/ui/button';
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
	DialogDescription,
	DialogFooter,
} from '@upstream/components/ui/dialog';
import { Field, FieldGroup, FieldLabel } from '@upstream/components/ui/field.tsx';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@upstream/components/ui/select';
import { useCredentials } from '@upstream/hooks/useCredentials';
import { useTranslation } from '@upstream/i18n/useI18n.ts';

interface Props {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onCreated?: () => void;
	defaultType?: string;
}

export function CreateCredentialDialog({ open, onOpenChange, onCreated, defaultType }: Props) {
	const { create } = useCredentials();
	const { t } = useTranslation();
	const [schemas, setSchemas] = useState<CredentialSchema[]>([]);
	const [loadingSchemas, setLoadingSchemas] = useState(false);
	const [selectedType, setSelectedType] = useState('');
	const [values, setValues] = useState<Record<string, SchemaFormValue>>({});
	const [submitting, setSubmitting] = useState(false);

	useEffect(() => {
		if (!open) return;
		setLoadingSchemas(true);
		credentialApi
			.schemas()
			.then((res) => {
				setSchemas(res.schemas);
				if (res.schemas.length > 0) {
					const first = (res.schemas[0].properties.type?.const as string) ?? '';
					setSelectedType(defaultType ?? first);
				}
			})
			.finally(() => setLoadingSchemas(false));
	}, [open, defaultType]);

	const selectedSchema = schemas.find(
		(s) => (s.properties.type?.const as string) === selectedType,
	);

	const handleTypeChange = (type: string) => {
		setSelectedType(type);
		setValues({});
	};

	const handleSubmit = async () => {
		if (!selectedSchema) return;
		setSubmitting(true);
		try {
			const data: Record<string, unknown> = { type: selectedType };
			for (const [key, prop] of Object.entries(selectedSchema.properties)) {
				if (key === 'id' || key === 'type' || prop.const !== undefined) continue;
				const val = values[key];
				if (val !== undefined && val !== '') data[key] = val;
			}
			await create({ data });
			onOpenChange(false);
			onCreated?.();
		} finally {
			setSubmitting(false);
		}
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="!w-[500px] !max-w-[500px]">
				<DialogHeader>
					<DialogTitle>{t('dialog-credential-create.title')}</DialogTitle>
					<DialogDescription>
						{t('dialog-credential-create.description')}
					</DialogDescription>
				</DialogHeader>
				<FieldGroup>
					<Field>
						<FieldLabel>{t('dialog-credential-create.selectType')}</FieldLabel>
						<Select
							value={selectedType}
							onValueChange={handleTypeChange}
							disabled={loadingSchemas}
						>
							<SelectTrigger>
								<SelectValue
									placeholder={
										loadingSchemas
											? t('common.loading')
											: t('dialog-credential-create.selectTypePlaceholder')
									}
								/>
							</SelectTrigger>
							<SelectContent>
								{schemas.map((s) => (
									<SelectItem
										key={s.properties.type?.const as string}
										value={s.properties.type?.const as string}
									>
										{s.title}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
					</Field>
					{selectedSchema && (
						<SchemaForm
							schema={selectedSchema}
							values={values}
							onChange={(key, val) => setValues((prev) => ({ ...prev, [key]: val }))}
						/>
					)}
				</FieldGroup>
				<DialogFooter>
					<Button
						variant="ghost"
						onClick={() => onOpenChange(false)}
						disabled={submitting}
					>
						<CircleAlert className="size-3.5" />
						{t('common.cancel')}
					</Button>
					<Button onClick={handleSubmit} disabled={submitting || !selectedSchema}>
						{submitting ? (
							<Loader2 className="size-3.5 animate-spin" />
						) : (
							<PlusCircle className="size-3.5" />
						)}
						{submitting ? t('common.creating') : t('common.create')}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
