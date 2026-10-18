import { toast } from 'sonner';

type AgentClientAuth = {
	baseUrl: string;
	getAccessToken: () => string | null;
	refreshAccessToken: () => Promise<string>;
};

let auth: AgentClientAuth = {
	baseUrl: import.meta.env.VITE_AGENT_SERVICE_BASE_URL ?? 'http://127.0.0.1:8001',
	getAccessToken: () => null,
	refreshAccessToken: async () => { throw new Error('Not authenticated'); },
};

export function configureAgentClient(next: AgentClientAuth): void {
	auth = next;
}

export const getBaseUrl = () => auth.baseUrl;
export const getUserId = () => '';

/**
 * Structured error thrown for non-2xx HTTP responses.
 * `message` contains the human-readable detail extracted from the backend.
 */
export class ApiError extends Error {
	readonly status: number;
	readonly detail: string;

	constructor(status: number, detail: string) {
		super(detail);
		this.name = 'ApiError';
		this.status = status;
		this.detail = detail;
	}
}

interface RequestOptions {
	method?: string;
	body?: unknown;
	params?: Record<string, string>;
	/** When true, suppresses the automatic error toast. Useful when the caller shows its own inline error UI. */
	silent?: boolean;
	signal?: AbortSignal;
	/** Overrides the stored server URL. Lets the setup page probe an address before persisting it. */
	baseUrl?: string;
	/** Overrides the stored username, for the same reason as `baseUrl`. */
	userId?: string;
	/** Gives up after this many ms and reports {@link TIMEOUT_STATUS}. Off by default — a streaming chat is meant to stay open. */
	timeoutMs?: number;
}

/** Reported when `timeoutMs` elapses. Real 408s come from a server, so either way the request did not complete in time. */
export const TIMEOUT_STATUS = 408;

function buildHeaders(hasBody: boolean): Record<string, string> {
	const token = auth.getAccessToken();
	const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
	if (hasBody) headers['Content-Type'] = 'application/json';
	return headers;
}

/** Parse the response body and extract the `detail` field if the backend returned JSON. */
async function extractErrorDetail(res: Response): Promise<string> {
	const text = await res.text();
	try {
		const json = JSON.parse(text) as { detail?: unknown };
		if (typeof json.detail === 'string') return json.detail;
		if (json.detail !== undefined) return JSON.stringify(json.detail);
	} catch {
		// not JSON – fall through
	}
	return text || res.statusText;
}

async function streamRequest(path: string, options: RequestOptions = {}): Promise<Response> {
	const {
		method = 'GET',
		body,
		params,
		signal,
		silent = false,
		baseUrl,
		userId: _userId,
		timeoutMs,
	} = options;
	const configuredBase = new URL(getBaseUrl());
	const url = new URL(path, baseUrl ?? configuredBase);
	if (baseUrl && new URL(baseUrl).origin !== configuredBase.origin || url.origin !== configuredBase.origin) {
		throw new Error('服务地址不匹配');
	}
	if (params) {
		Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
	}

	// AbortSignal.timeout aborts with a TimeoutError, which is what lets the
	// catch below tell "too slow" apart from the caller's own cancellation.
	const deadline = timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined;
	const combined =
		deadline && signal ? AbortSignal.any([signal, deadline]) : (deadline ?? signal);

	let res: Response;
	try {
		const send = () => fetch(url.toString(), {
			method,
			headers: buildHeaders(body !== undefined),
			body: body ? JSON.stringify(body) : undefined,
			signal: combined,
		});
		res = await send();
	} catch (e) {
		// An abort is the caller's own doing — pass it through untouched.
		if (e instanceof DOMException && e.name === 'AbortError') throw e;
		// A server that accepts the connection then stalls would otherwise
		// leave the caller waiting forever.
		const timedOut = e instanceof DOMException && e.name === 'TimeoutError';
		// Otherwise fetch only rejects when the request never reached the
		// server: wrong address, DNS failure, refused connection, blocked
		// preflight. Status 0 distinguishes that from any HTTP-level failure.
		const error = timedOut
			? new ApiError(TIMEOUT_STATUS, '请求超时，请重试')
			: new ApiError(
					0,
					'无法连接服务，请检查网络后重试',
				);
		if (!silent) toast.error(error.detail);
		throw error;
	}
	if (res.status === 401) {
		await auth.refreshAccessToken();
		res = await fetch(url.toString(), {
			method,
			headers: buildHeaders(body !== undefined),
			body: body ? JSON.stringify(body) : undefined,
			signal: combined,
		});
	}

	if (!res.ok) {
		const detail = await extractErrorDetail(res);
		const error = new ApiError(res.status, detail);
		if (!silent) toast.error(detail);
		throw error;
	}

	return res;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
	const res = await streamRequest(path, options);
	if (res.status === 204) return undefined as T;
	return res.json() as Promise<T>;
}

export const client = {
	get: <T>(
		path: string,
		params?: Record<string, string>,
		options?: { silent?: boolean; baseUrl?: string; userId?: string; timeoutMs?: number },
	) => request<T>(path, { method: 'GET', params, ...options }),
	post: <T>(
		path: string,
		body?: unknown,
		params?: Record<string, string>,
		options?: { silent?: boolean },
	) => request<T>(path, { method: 'POST', body, params, silent: options?.silent }),
	patch: <T>(
		path: string,
		body?: unknown,
		params?: Record<string, string>,
		options?: { silent?: boolean },
	) => request<T>(path, { method: 'PATCH', body, params, silent: options?.silent }),
	delete: <T = void>(path: string, params?: Record<string, string>) =>
		request<T>(path, { method: 'DELETE', params }),
	stream: (path: string, options?: RequestOptions) => streamRequest(path, options),
};
