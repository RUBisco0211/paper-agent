import type { Msg, ToolResultBlock } from '@agentscope-ai/agentscope/message';

/**
 * 正文里的引用标记。
 *
 * 标记是模型自己写进答案的，所以正文只能提供「位置」；哪些 id 算已登记，
 * 由本会话检索到的证据决定（`registeredCitations`），详情则在点击时才查。
 */

/** The id format `build_citation_id` issues; anything else is not a citation. */
const CITATION_ID = /^cit_[0-9a-f]{12}$/;

/** Same marker, global, for rewriting a text block. */
const CITATION_MARKER = /\[(cit_[0-9a-f]{12})\]/g;

/** Text a tool result carries, whether it is a string or text blocks. */
function resultText(block: ToolResultBlock): string {
	if (typeof block.output === 'string') return block.output;
	if (Array.isArray(block.output)) {
		return block.output.map((item) => (item.type === 'text' ? item.text : '')).join('\n');
	}
	return '';
}

/**
 * Citation ids this session actually registered.
 *
 * Read from every `search_papers` result in the loaded history — that tool is
 * the only one that registers citations, so its results are the ground truth
 * for what a marker may point at.
 *
 * @param messages - Every message loaded for the session.
 */
export function registeredCitations(messages: Msg[]): Set<string> {
	const ids = new Set<string>();
	for (const message of messages) {
		for (const block of message.content) {
			if (block.type !== 'tool_result' || block.name !== 'search_papers') continue;
			try {
				const data: unknown = JSON.parse(resultText(block));
				if (!data || typeof data !== 'object') continue;
				const evidence = (data as { evidence?: unknown }).evidence;
				if (!Array.isArray(evidence)) continue;
				for (const item of evidence) {
					const id = (item as { citation_id?: unknown } | null)?.citation_id;
					if (typeof id === 'string' && CITATION_ID.test(id)) ids.add(id);
				}
			} catch {
				// A result that is not JSON carries no citations.
				continue;
			}
		}
	}
	return ids;
}

/** Splits a text block into prose and code so literals in code stay literal. */
const CODE_SPAN = /(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/;

/**
 * Rewrite the markers an answer already carries into inline tags.
 *
 * The text supplies the position; an id only becomes a chip when this session
 * registered it, so a marker the model invented stays plain text. Numbers are
 * handed out in reading order and reused for repeats.
 *
 * @param text - One text block of the answer.
 * @param known - Ids registered by this session's searches.
 * @param order - Numbers handed out so far, shared across the message's blocks.
 */
export function renderCitationTags(
	text: string,
	known: ReadonlySet<string>,
	order: Map<string, number>,
): string {
	return text
		.split(CODE_SPAN)
		.map((part, index) => {
			if (index % 2 === 1) return part;
			return part.replace(CITATION_MARKER, (marker, id: string) => {
				if (!known.has(id)) return marker;
				let number = order.get(id);
				if (number === undefined) {
					number = order.size + 1;
					order.set(id, number);
				}
				return `<paper-citation data-cid="${id}">[${number}]</paper-citation>`;
			});
		})
		.join('');
}
