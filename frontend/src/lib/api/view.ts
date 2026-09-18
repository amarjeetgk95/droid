import { z } from 'zod';

export const STREAM_PRIORITIES = ['P0', 'P1', 'P2'] as const;
export const StreamPrioritySchema = z.enum(STREAM_PRIORITIES);

export const CommandSectionEnvelopeSchema = z.object({
  value: z.unknown(),
  updated_at: z.string(),
  freshness_s: z.number(),
  degraded: z.boolean(),
  version: z.number(),
});

export const COMMAND_VIEW_SECTIONS = [
  'market',
  'regime',
  'signals',
  'feed_health',
  'kill_switch',
  'ml',
  'risk_events',
] as const;

export const COMMAND_SECTION_ENVELOPE_KEYS = [
  'value',
  'updated_at',
  'freshness_s',
  'degraded',
  'version',
] as const;

export const CommandViewSchema = z.object({
  view: z.literal('command'),
  view_version: z.number(),
  generated_at: z.string(),
  degraded: z.boolean(),
  sections: z.record(z.string(), CommandSectionEnvelopeSchema),
  hints: z.array(z.unknown()),
  errors: z.record(z.string(), z.string()),
});

export const StreamFrameSchema = z.object({
  event: z.string(),
  data: z.unknown(),
  priority: StreamPrioritySchema,
  seq: z.number(),
  timestamp: z.number(),
});

export const AppHintSchema = z.object({
  id: z.string(),
  severity: z.string().optional(),
  action_required: z.boolean().optional(),
  target: z.string().optional(),
});

export const ViewSectionChangedDataSchema = z.object({
  section: z.string(),
  version: z.number(),
  value: z.unknown(),
  updated_at: z.string(),
  freshness_s: z.number(),
  degraded: z.boolean(),
});
export const ViewSectionChangedFrameSchema = StreamFrameSchema.extend({
  event: z.literal('view.section.changed'),
  data: ViewSectionChangedDataSchema,
});

export const SignalEventDataSchema = z.object({
  event: z.string(),
  data: z.unknown(),
  priority: StreamPrioritySchema,
  seq: z.number(),
  timestamp: z.number(),
});
export const SignalEventFrameSchema = StreamFrameSchema.extend({
  event: z.literal('signal.event'),
  data: SignalEventDataSchema,
});

export const HeartbeatDataSchema = z.object({ status: z.string() });
export const HeartbeatFrameSchema = StreamFrameSchema.extend({
  event: z.literal('heartbeat'),
  data: HeartbeatDataSchema,
});

export const HintRaisedDataSchema = z.object({ hint: AppHintSchema });
export const HintRaisedFrameSchema = StreamFrameSchema.extend({
  event: z.literal('hint.raised'),
  data: HintRaisedDataSchema,
});

export const HintClearedDataSchema = z.object({ id: z.string() });
export const HintClearedFrameSchema = StreamFrameSchema.extend({
  event: z.literal('hint.cleared'),
  data: HintClearedDataSchema,
});

export type StreamPriority = z.infer<typeof StreamPrioritySchema>;
export type CommandSectionEnvelope = z.infer<typeof CommandSectionEnvelopeSchema>;
export type CommandView = z.infer<typeof CommandViewSchema>;
export type StreamFrame = z.infer<typeof StreamFrameSchema>;
export type AppHint = z.infer<typeof AppHintSchema>;
export type ViewSectionChangedData = z.infer<typeof ViewSectionChangedDataSchema>;
export type ViewSectionChangedFrame = z.infer<typeof ViewSectionChangedFrameSchema>;
export type SignalEventData = z.infer<typeof SignalEventDataSchema>;
export type SignalEventFrame = z.infer<typeof SignalEventFrameSchema>;
export type HeartbeatFrame = z.infer<typeof HeartbeatFrameSchema>;
export type HintRaisedFrame = z.infer<typeof HintRaisedFrameSchema>;
export type HintClearedFrame = z.infer<typeof HintClearedFrameSchema>;

export function parseCommandView(input: unknown): CommandView | null {
  const result = CommandViewSchema.safeParse(input);
  return result.success ? result.data : null;
}

export function parseStreamFrame(input: unknown): StreamFrame | null {
  const result = StreamFrameSchema.safeParse(input);
  return result.success ? result.data : null;
}

export function parseViewSectionChangedFrame(input: unknown): ViewSectionChangedFrame | null {
  const result = ViewSectionChangedFrameSchema.safeParse(input);
  return result.success ? result.data : null;
}

export function parseSignalEventFrame(input: unknown): SignalEventFrame | null {
  const result = SignalEventFrameSchema.safeParse(input);
  return result.success ? result.data : null;
}

export function parseHeartbeatFrame(input: unknown): HeartbeatFrame | null {
  const result = HeartbeatFrameSchema.safeParse(input);
  return result.success ? result.data : null;
}

export function parseHintRaisedFrame(input: unknown): HintRaisedFrame | null {
  const result = HintRaisedFrameSchema.safeParse(input);
  return result.success ? result.data : null;
}

export function parseHintClearedFrame(input: unknown): HintClearedFrame | null {
  const result = HintClearedFrameSchema.safeParse(input);
  return result.success ? result.data : null;
}
