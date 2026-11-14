import type { Message, Segment } from './types';

export const transcriptKinds = [
  {id: 'system', label: 'System prompt'},
  {id: 'user', label: 'User prompt'},
  {id: 'reasoning', label: 'Reasoning'},
  {id: 'assistant', label: 'Assistant output'},
  {id: 'tool-call', label: 'Tool call'},
  {id: 'tool', label: 'Tool result'},
  {id: 'event', label: 'Run info'},
] as const;
export function segmentKind(message: Message, segment: Segment) {
  if (segment.kind === 'reasoning') return 'reasoning';
  if (segment.kind === 'command') return 'tool-call';
  return message.role;
}
export function messageKind(message: Message) {
  const kinds = new Set(message.segments.map(s => segmentKind(message, s)));
  return kinds.size === 1 ? [...kinds][0]! : message.role;
}
export const kindLabel = (kind: string) => transcriptKinds.find(k => k.id === kind)?.label ?? kind;
