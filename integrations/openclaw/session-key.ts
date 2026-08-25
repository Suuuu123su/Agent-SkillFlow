export function openClawSessionKey(scenarioId: string, sessionId: string): string {
  return `agent:main:openresponses:t15-${scenarioId}-${sessionId}`.toLowerCase();
}
