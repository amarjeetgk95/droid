'use client';

import React, { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import { AIChatMessage, AIChatStreamChunk } from '@/lib/types';
import { getStoredSettings } from '@/lib/settings';
import {
 Sparkles,
 X,
 Send,
 Square,
 Bot,
 User,
 ChevronDown,
 ChevronUp,
 Brain,
 Wrench,
 RotateCcw,
 Maximize2,
 Minimize2,
 Activity,
 AlertCircle,
} from 'lucide-react';

interface AICopilotDrawerProps {
 currentSymbol?: string;
 currentPageContext?: string;
}

export function AICopilotDrawer({
 currentSymbol = 'NIFTY',
 currentPageContext = 'Dashboard',
}: AICopilotDrawerProps) {
 const [isOpen, setIsOpen] = useState(false);
 const [isExpanded, setIsExpanded] = useState(false);
 const [messages, setMessages] = useState<AIChatMessage[]>([
 {
  role: 'assistant',
  content: `Hello trader! I am your **DROID AI Copilot**. I have direct access to live technical indicators, 4-quadrant futures buildup, option Greeks, and institutional positioning for **${currentSymbol}**.\n\nHow can I assist your market analysis today?`,
 },
 ]);
 const [input, setInput] = useState('');
 const [isStreaming, setIsStreaming] = useState(false);
 const [streamingReasoning, setStreamingReasoning] = useState('');
 const [streamingContent, setStreamingContent] = useState('');
 const [activeToolName, setActiveToolName] = useState<string | null>(null);
 const [expandedReasoningMap, setExpandedReasoningMap] = useState<Record<number, boolean>>({});
 const [isStreamingReasoningOpen, setIsStreamingReasoningOpen] = useState(true);

 const abortControllerRef = useRef<AbortController | null>(null);
 const messagesEndRef = useRef<HTMLDivElement>(null);
 const inputRef = useRef<HTMLTextAreaElement>(null);

 // Keyboard shortcut (Ctrl+Space or Cmd+K) to toggle Copilot
 useEffect(() => {
 const handleKeyDown = (e: KeyboardEvent) => {
  if ((e.ctrlKey && e.code === 'Space') || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) {
  const target = e.target as HTMLElement;
  if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) {
   // If typing in another input, don't hijack unless it's Ctrl+Space
   if (e.key.toLowerCase() === 'k') return;
  }
  e.preventDefault();
  setIsOpen((prev) => !prev);
  }
 };
 window.addEventListener('keydown', handleKeyDown);
 return () => window.removeEventListener('keydown', handleKeyDown);
 }, []);

 // Auto scroll to bottom
 useEffect(() => {
 messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
 }, [messages, streamingContent, streamingReasoning, activeToolName]);

 // Focus input when opened
 useEffect(() => {
 if (isOpen) {
  setTimeout(() => inputRef.current?.focus(), 150);
 }
 }, [isOpen]);

 const quickPrompts = [
 `Analyze current ${currentSymbol} trend & key pivot levels`,
 `What are the key Call resistance and Put support walls?`,
 `Evaluate 4-quadrant futures buildup and rollover pace`,
 `Recommend a delta-neutral options spread for current IV`,
 ];

 const handleSend = async (textToSend?: string) => {
 const text = (textToSend || input).trim();
 if (!text || isStreaming) return;

 const userMessage: AIChatMessage = { role: 'user', content: text };
 const newMessages = [...messages, userMessage];
 setMessages(newMessages);
 setInput('');
 setIsStreaming(true);
 setStreamingContent('');
 setStreamingReasoning('');
 setActiveToolName(null);
 setIsStreamingReasoningOpen(true);

 const abortController = new AbortController();
 abortControllerRef.current = abortController;

 const settings = getStoredSettings();
 const provider = settings.ai.provider === 'mock_ai' ? 'openrouter' : (settings.ai.provider || 'openrouter');
 const model = settings.ai.openRouterSelectedModel || 'auto';

 let currentReasoning = '';
 let currentContent = '';

 await api.streamAIChat(
  {
  messages: newMessages,
  symbol: currentSymbol,
  provider,
  model,
  context_page: currentPageContext,
  enable_tools: true,
  openrouter_api_key: settings.ai.openRouterApiKey || undefined,
  gemini_api_key: settings.ai.geminiApiKey || undefined,
  },
  (chunk: AIChatStreamChunk) => {
  if (chunk.type === 'reasoning' && chunk.reasoning_delta) {
   currentReasoning += chunk.reasoning_delta;
   setStreamingReasoning(currentReasoning);
  } else if (chunk.type === 'content' && chunk.delta) {
   currentContent += chunk.delta;
   setStreamingContent(currentContent);
  } else if (chunk.type === 'tool_call' && chunk.tool_call) {
   const fnName = chunk.tool_call.function?.name || 'quant_engine';
   setActiveToolName(fnName);
  } else if (chunk.type === 'tool_result') {
   setActiveToolName(null);
  } else if (chunk.type === 'error') {
   currentContent += `\n\n⚠️ **Error:** ${chunk.delta}`;
   setStreamingContent(currentContent);
  }
  },
  (err: string) => {
  setIsStreaming(false);
  setActiveToolName(null);
  setMessages((prev) => [
   ...prev,
   {
   role: 'assistant',
   content: currentContent ? `${currentContent}\n\n⚠️ *${err}*` : `⚠️ **Connection Error:** ${err}`,
   reasoning_content: currentReasoning || null,
   },
  ]);
  setStreamingContent('');
  setStreamingReasoning('');
  },
  () => {
  setIsStreaming(false);
  setActiveToolName(null);
  if (currentContent || currentReasoning) {
   setMessages((prev) => [
   ...prev,
   {
    role: 'assistant',
    content: currentContent || 'Analysis completed.',
    reasoning_content: currentReasoning || null,
   },
   ]);
  }
  setStreamingContent('');
  setStreamingReasoning('');
  },
  abortController.signal
 );
 };

 const handleStop = () => {
 if (abortControllerRef.current) {
  abortControllerRef.current.abort();
  abortControllerRef.current = null;
 }
 setIsStreaming(false);
 setActiveToolName(null);
 if (streamingContent || streamingReasoning) {
  setMessages((prev) => [
  ...prev,
  {
   role: 'assistant',
   content: streamingContent || '*Generation stopped by user.*',
   reasoning_content: streamingReasoning || null,
  },
  ]);
 }
 setStreamingContent('');
 setStreamingReasoning('');
 };

 const handleClearHistory = () => {
 setMessages([
  {
  role: 'assistant',
  content: `Chat cleared. Ready for your next query on **${currentSymbol}**.`,
  },
 ]);
 };

 const toggleReasoning = (idx: number) => {
 setExpandedReasoningMap((prev) => ({ ...prev, [idx]: !prev[idx] }));
 };

 return (
 <>
  {/* Floating Trigger Button */}
  {!isOpen && (
  <button
   onClick={() => setIsOpen(true)}
   className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-primary to-indigo-600 text-white rounded-full shadow-xl hover:shadow-sm hover:scale-105 transition-all duration-200 cursor-pointer group"
   title="Open AI Copilot (Ctrl+Space)"
  >
   <Sparkles className="w-4 h-4 animate-pulse group-hover:rotate-12 transition-transform" />
   <span className="text-xs font-bold tracking-wide">AI Copilot</span>
   <span className="text-[10px] bg-white/20 px-1.5 py-0.5 rounded font-mono">
   {currentSymbol}
   </span>
  </button>
  )}

  {/* Copilot Drawer */}
  {isOpen && (
  <div
   className={`fixed inset-y-0 right-0 z-50 flex flex-col bg-background/95 border-l border-border shadow-sm transition-all duration-300 ${
   isExpanded ? 'w-full md:w-[720px]' : 'w-full sm:w-[460px]'
   }`}
  >
   {/* Header */}
   <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-card/60">
   <div className="flex items-center gap-2">
    <div className="p-1.5 bg-primary/10 rounded-lg text-primary">
    <Brain className="w-5 h-5" />
    </div>
    <div>
    <div className="flex items-center gap-2">
     <h3 className="text-sm font-bold text-foreground">DROID Copilot</h3>
     <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-primary/10 text-primary font-semibold border border-primary/20">
     {currentSymbol}
     </span>
    </div>
    <p className="text-[10px] text-muted-foreground">
     Context: {currentPageContext} • Quant Tools Active
    </p>
    </div>
   </div>

   <div className="flex items-center gap-1 text-muted-foreground">
    <button
    onClick={handleClearHistory}
    className="p-1.5 hover:bg-secondary rounded-lg transition-colors"
    title="Clear Chat History"
    >
    <RotateCcw className="w-4 h-4" />
    </button>
    <button
    onClick={() => setIsExpanded((prev) => !prev)}
    className="p-1.5 hover:bg-secondary rounded-lg transition-colors hidden sm:block"
    title={isExpanded ? 'Narrow Drawer' : 'Expand Drawer'}
    >
    {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
    </button>
    <button
    onClick={() => setIsOpen(false)}
    className="p-1.5 hover:bg-secondary rounded-lg transition-colors"
    title="Close Drawer"
    >
    <X className="w-4 h-4" />
    </button>
   </div>
   </div>

   {/* Quick Prompts Carousel */}
   <div className="px-4 py-2 bg-secondary/20 border-b border-border/50 flex gap-2 overflow-x-auto no-scrollbar">
   {quickPrompts.map((p, i) => (
    <button
    key={i}
    onClick={() => handleSend(p)}
    disabled={isStreaming}
    className="whitespace-nowrap px-2.5 py-1 text-[11px] rounded-full bg-secondary/80 hover:bg-primary/10 hover:text-primary hover:border-primary/30 border border-border transition-all cursor-pointer disabled:opacity-50 text-muted-foreground"
    >
    {p}
    </button>
   ))}
   </div>

   {/* Chat Messages */}
   <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
   {messages.map((m, idx) => (
    <div
    key={idx}
    className={`flex gap-3 ${
     m.role === 'user' ? 'justify-end' : 'justify-start'
    }`}
    >
    {m.role !== 'user' && (
     <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0 mt-0.5">
     <Bot className="w-4 h-4" />
     </div>
    )}

    <div
     className={`max-w-[85%] rounded-2xl px-4 py-3 space-y-2 ${
     m.role === 'user'
      ? 'bg-primary text-primary-foreground font-medium rounded-br-xs'
      : 'bg-card border border-border/80 text-foreground rounded-bl-xs shadow-xs'
     }`}
    >
     {/* Collapsible DeepSeek Reasoning Token Block */}
     {m.reasoning_content && (
     <div className="rounded-lg bg-secondary/40 border border-border/60 overflow-hidden text-[11px]">
      <button
      onClick={() => toggleReasoning(idx)}
      className="w-full flex items-center justify-between px-2.5 py-1.5 bg-secondary/60 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
      >
      <span className="flex items-center gap-1.5 font-semibold">
       <Brain className="w-3.5 h-3.5 text-primary" />
       Quantitative Reasoning Chain
      </span>
      {expandedReasoningMap[idx] ? (
       <ChevronUp className="w-3.5 h-3.5" />
      ) : (
       <ChevronDown className="w-3.5 h-3.5" />
      )}
      </button>
      {expandedReasoningMap[idx] && (
      <div className="p-2.5 text-muted-foreground font-mono text-[10.5px] leading-relaxed border-t border-border/40 whitespace-pre-wrap max-h-48 overflow-y-auto">
       {m.reasoning_content}
      </div>
      )}
     </div>
     )}

     {/* Message Content */}
     <div className="leading-relaxed whitespace-pre-wrap font-sans">
     {m.content}
     </div>
    </div>

    {m.role === 'user' && (
     <div className="w-7 h-7 rounded-lg bg-secondary border border-border flex items-center justify-center text-foreground shrink-0 mt-0.5">
     <User className="w-4 h-4" />
     </div>
    )}
    </div>
   ))}

   {/* Live Streaming Assistant Message */}
   {isStreaming && (
    <div className="flex gap-3 justify-start">
    <div className="w-7 h-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0 mt-0.5 animate-pulse">
     <Bot className="w-4 h-4" />
    </div>

    <div className="max-w-[85%] rounded-2xl px-4 py-3 space-y-2 bg-card border border-primary/30 text-foreground rounded-bl-xs shadow-sm">
     {/* Active Tool Execution Pill */}
     {activeToolName && (
     <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-amber-500/10 text-amber-600 border border-amber-500/20 text-[11px] font-mono animate-pulse">
      <Wrench className="w-3.5 h-3.5 animate-spin" />
      Invoking tool: {activeToolName}...
     </div>
     )}

     {/* Live Streaming Reasoning Block */}
     {streamingReasoning && (
     <div className="rounded-lg bg-secondary/40 border border-border/60 overflow-hidden text-[11px]">
      <button
      onClick={() => setIsStreamingReasoningOpen((prev) => !prev)}
      className="w-full flex items-center justify-between px-2.5 py-1.5 bg-secondary/60 text-muted-foreground hover:text-foreground cursor-pointer"
      >
      <span className="flex items-center gap-1.5 font-semibold text-primary">
       <Brain className="w-3.5 h-3.5 animate-bounce" />
       Thinking & Synthesizing...
      </span>
      {isStreamingReasoningOpen ? (
       <ChevronUp className="w-3.5 h-3.5" />
      ) : (
       <ChevronDown className="w-3.5 h-3.5" />
      )}
      </button>
      {isStreamingReasoningOpen && (
      <div className="p-2.5 text-muted-foreground font-mono text-[10.5px] leading-relaxed border-t border-border/40 whitespace-pre-wrap max-h-40 overflow-y-auto">
       {streamingReasoning}
      </div>
      )}
     </div>
     )}

     {/* Live Streaming Content */}
     <div className="leading-relaxed whitespace-pre-wrap font-sans">
     {streamingContent}
     <span className="inline-block w-2 h-3.5 ml-1 bg-primary animate-pulse" />
     </div>
    </div>
    </div>
   )}

   <div ref={messagesEndRef} />
   </div>

   {/* Input Area */}
   <div className="p-3 border-t border-border bg-card/70">
   <div className="relative flex items-end gap-2 bg-secondary/40 border border-border rounded-xl p-2 focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/50 transition-all">
    <textarea
    ref={inputRef}
    value={input}
    onChange={(e) => setInput(e.target.value)}
    onKeyDown={(e) => {
     if (e.key === 'Enter' && !e.shiftKey) {
     e.preventDefault();
     handleSend();
     }
    }}
    placeholder={`Ask Copilot about ${currentSymbol} (e.g. key walls, regime, option spreads)...`}
    className="w-full max-h-32 min-h-[44px] resize-none bg-transparent border-none text-xs focus:outline-hidden text-foreground placeholder:text-muted-foreground/70 p-1"
    rows={2}
    disabled={isStreaming}
    />

    {isStreaming ? (
    <button
     type="button"
     onClick={handleStop}
     className="p-2 bg-destructive text-destructive-foreground rounded-lg hover:bg-destructive/90 transition-colors shrink-0"
     title="Stop generation"
    >
     <Square className="w-4 h-4 fill-current" />
    </button>
    ) : (
    <button
     type="button"
     onClick={() => handleSend()}
     disabled={!input.trim()}
     className="p-2 bg-primary text-primary-foreground rounded-lg disabled:opacity-40 hover:bg-primary/90 transition-colors shrink-0 cursor-pointer"
     title="Send message"
    >
     <Send className="w-4 h-4" />
    </button>
    )}
   </div>

   <div className="flex items-center justify-between text-[10px] text-muted-foreground mt-2 px-1">
    <span>Press <kbd className="font-mono bg-secondary px-1 py-0.5 rounded border">Enter</kbd> to send</span>
    <span className="flex items-center gap-1">
    <Activity className="w-3 h-3 text-primary" />
    Live Agent Active
    </span>
   </div>
   </div>
  </div>
  )}
 </>
 );
}
