/**
 * 会话输入里的 @ 文献提及。
 *
 * 输入框用 chip 承载提及，正文里保留可读的 `@标题`；发送时换成 `@{{n}}`，
 * 由服务端核验归属与范围后替换成带 paper id 的引用（0099）。
 */
export interface MentionCandidate {
	user_paper_id: string;
	title: string;
}

/** A chip reads as `@标题` in the plain text of the editor. */
function mentionToken(mention: MentionCandidate): string {
	return `@${mention.title}`;
}

/**
 * Rewrite every readable token into `@{{n}}`, numbered 1..n in document order.
 *
 * Returns the mentions actually found so the caller's payload indices always
 * match the placeholders in the text: a token the user already deleted must not
 * leave a gap in the numbering.
 *
 * @param text - Plain text of the editor, chips included.
 * @param mentions - Mentions in document order.
 */
export function mentionPlaceholders(
	text: string,
	mentions: MentionCandidate[],
): { text: string; mentions: MentionCandidate[] } {
	const present: MentionCandidate[] = [];
	let cursor = 0;
	let body = '';
	for (const mention of mentions) {
		const token = mentionToken(mention);
		const at = text.indexOf(token, cursor);
		if (at < 0) continue;
		present.push(mention);
		body += `${text.slice(cursor, at)}@{{${present.length}}}`;
		cursor = at + token.length;
	}
	return { text: body + text.slice(cursor), mentions: present };
}

/** The payload shape `POST /chat/` expects for each mention. */
export function mentionRequest(mentions: MentionCandidate[]) {
	return mentions.map((mention, index) => ({
		index: index + 1,
		user_paper_id: mention.user_paper_id,
	}));
}

/**
 * Metadata mirrored onto a locally sent message, so its own bubble can show
 * the same chips the service records on the way back.
 */
export function mentionMetadata(mentions: MentionCandidate[]) {
	return mentions.map((mention, index) => ({
		index: index + 1,
		user_paper_id: mention.user_paper_id,
		title: mention.title,
	}));
}

/** One mention as the service recorded it on a sent user message. */
export interface MessageMention {
	index: number;
	user_paper_id: string;
	title: string;
	has_fulltext: boolean;
}

/** Read the mentions the service stored beside the message body. */
export function readMessageMentions(metadata: unknown): MessageMention[] {
	if (!metadata || typeof metadata !== 'object') return [];
	const paperAgent = (metadata as Record<string, unknown>).paper_agent;
	if (!paperAgent || typeof paperAgent !== 'object') return [];
	const items = (paperAgent as Record<string, unknown>).mentions;
	if (!Array.isArray(items)) return [];
	return items.flatMap((item): MessageMention[] => {
		if (!item || typeof item !== 'object') return [];
		const value = item as Record<string, unknown>;
		if (typeof value.index !== 'number' || typeof value.user_paper_id !== 'string') return [];
		return [{
			index: value.index,
			user_paper_id: value.user_paper_id,
			title: typeof value.title === 'string' && value.title ? value.title : '未命名文献',
			has_fulltext: value.has_fulltext === true,
		}];
	});
}

/** Chips show this much of a title; the full one stays in the hover title. */
const CHIP_TITLE_LENGTH = 24;

/** Shorten a paper title to what a chip can show without taking a whole line. */
export function mentionLabel(title: string): string {
	return title.length > CHIP_TITLE_LENGTH ? `${title.slice(0, CHIP_TITLE_LENGTH)}…` : title;
}

function escapeRegExp(value: string): string {
	return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escapeHtml(value: string): string {
	return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Rewrite every `@《标题》(paper:id)` the service wrote into the caller's form.
 *
 * The marker is matched from the recorded mention rather than a blanket text
 * pattern, so a title that merely looks like a marker stays untouched. The
 * `（待补全文）` hint the service appends is model-facing and is dropped here.
 *
 * A message this tab just sent still carries the readable `@标题` token (the
 * service rewrites it only on the way back), so that form is accepted as a
 * fallback for the same recorded mention.
 *
 * @param text - Message body as the service stored it.
 * @param mentions - Mentions recorded for this message.
 * @param render - What one mention becomes; may return markup.
 */
export function renderMessageMentions(
	text: string,
	mentions: MessageMention[],
	render: (mention: MessageMention) => string,
): string {
	let result = text;
	for (const mention of mentions) {
		const marker = new RegExp(
			`@《${escapeRegExp(mention.title)}》\\(paper:${escapeRegExp(mention.user_paper_id)}\\)(?:（待补全文）)?`,
			'g',
		);
		const replaced = result.replace(marker, () => render(mention));
		if (replaced !== result) {
			result = replaced;
			continue;
		}
		const token = `@${mention.title}`;
		if (mention.title && result.includes(token)) {
			result = result.replaceAll(token, () => render(mention));
		}
	}
	return result;
}

/** The inline chip markup a rendered message carries for one mention. */
export function mentionTag(mention: MessageMention): string {
	return `<paper-mention title="${escapeHtml(mention.title)}">@${escapeHtml(mentionLabel(mention.title))}</paper-mention>`;
}

