import type { AITaskId, DirectProviderId } from '@/lib/settings';

export const TASK_LABELS: Record<AITaskId, { label: string; hint: string }> = {
  INTRADAY_ANALYSIS: { label: 'Intraday Analysis', hint: 'fast finance/reasoning' },
  NEWS_ANALYSIS: { label: 'News Analysis', hint: 'research/news model' },
  DEEP_RESEARCH: { label: 'Deep Research', hint: 'strongest reasoning' },
  MTF_SYNTHESIS: { label: 'MTF Synthesis', hint: 'synthesis model' },
  CHART_EXPLANATION: { label: 'Chart Explanation', hint: 'fast model' },
  FINAL_REVIEW: { label: 'Final Review', hint: 'highest quality' },
};

export const DIRECT_PROVIDER_OPTIONS: { id: DirectProviderId; name: string; desc: string }[] = [
  { id: 'OpenAI', name: 'OpenAI', desc: 'GPT-4o / GPT-4o-mini via api.openai.com' },
  { id: 'Novita AI', name: 'Novita AI', desc: 'Llama / Qwen via Novita' },
  { id: 'NVIDIA', name: 'NVIDIA', desc: 'Llama / Nemotron via NIM' },
  { id: 'Google Gemini', name: 'Google Gemini', desc: 'Gemini 2.5 via Google AI' },
  { id: 'Custom OpenAI-Compatible', name: 'Custom OpenAI-Compatible', desc: 'Any OpenAI-compatible base URL' },
];
