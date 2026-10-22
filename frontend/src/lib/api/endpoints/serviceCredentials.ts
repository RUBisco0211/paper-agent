import type { ApiClient } from "../client"

const PATH = "/v1/service-credentials"

export interface ServiceCredential {
  kind: string
  label: string
  fields: Record<string, string>
}

export interface ServiceCredentialList {
  items: ServiceCredential[]
}

export function serviceCredentialEndpoints(client: ApiClient) {
  return {
    list: () => client.request<ServiceCredentialList>(PATH),
    save: (kind: string, body: { label?: string; fields: Record<string, string> }) =>
      client.request<ServiceCredential>(`${PATH}/${kind}`, {
        method: "PUT",
        json: { kind, label: body.label ?? "", fields: body.fields },
      }),
    remove: (kind: string) => client.request<void>(`${PATH}/${kind}`, { method: "DELETE" }),
  }
}
