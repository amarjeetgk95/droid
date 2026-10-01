'use client';

import { useMemo, useState } from 'react';
import { Plus, Trash2, Wand2, Braces } from 'lucide-react';
import type { OperatorDoc, RuleCondition, RuleGroup, RuleOperand, RuleSet } from '@/lib/api/indicatorResearch';
import { cloneRules, condition, describeRule, group, isGroup } from '@/lib/indicatorResearch';

type Props = {
  rules: RuleSet;
  onChange: (rules: RuleSet) => void;
  mode: 'auto' | 'custom';
  onModeChange: (mode: 'auto' | 'custom') => void;
  onUseDefaults: () => void;
  operators: OperatorDoc[];
  features: string[];
  ruleSummary: { long: string; short: string } | null;
  problems: { long: string[]; short: string[] } | null;
  indicatorName: string | null;
};

const UNARY = new Set(['turns_up', 'turns_down', 'rising', 'falling', 'slope_up', 'slope_down', 'is_true', 'is_false']);
const RANGE = new Set(['in_range', 'outside_range']);

/**
 * Rules are edited as a tree that serialises straight to the JSON the backend
 * evaluates. Nothing here is executable code — the safety test asserts the
 * module never accepts one.
 */
export function SignalBuilder({
  rules,
  onChange,
  mode,
  onModeChange,
  onUseDefaults,
  operators,
  features,
  ruleSummary,
  problems,
  indicatorName,
}: Props) {
  const [showJson, setShowJson] = useState(false);

  const opDocs = useMemo(() => {
    const map = new Map<string, OperatorDoc>();
    for (const doc of operators) map.set(doc.name, doc);
    return map;
  }, [operators]);

  const binaryOps = useMemo(() => operators.filter((o) => !UNARY.has(o.name)), [operators]);

  const patchSide = (side: 'long' | 'short', node: RuleGroup | null) => {
    const next = cloneRules(rules);
    next[side] = node;
    onChange(next);
  };

  const setEnabled = (side: 'long' | 'short', enabled: boolean) => {
    if (enabled) {
      patchSide(side, group('AND', [condition(features[0] ?? 'close', 'crosses_above', 0)]));
    } else {
      patchSide(side, null);
    }
    onModeChange('custom');
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1.5">
        <span className="micro-label">Signal logic</span>
        <span className={`badge badge-sm ${mode === 'auto' ? 'b-info' : 'b-warn'}`} title="Auto = the indicator's own declared default rules">
          {mode === 'auto' ? 'indicator defaults' : 'custom'}
        </span>
        <button type="button" className="btn-ic ml-auto" onClick={onUseDefaults} title="Replace with the indicator's declared default rules">
          <Wand2 size={11} />
        </button>
        <button type="button" className="btn-ic" onClick={() => setShowJson((v) => !v)} title="Show the structured JSON sent to the backend">
          <Braces size={11} />
        </button>
      </div>

      <p className="sg-note">
        Rules are stored as structured JSON. {indicatorName ? `Currently analysing ${indicatorName}.` : 'Select an indicator to begin.'}
      </p>

      {(['long', 'short'] as const).map((side) => {
        const node = rules[side] ?? null;
        const enabled = node !== null;
        return (
          <div key={side} className={`rounded-md border px-2 py-2 ${side === 'long' ? 'border-up-line bg-up-wash' : 'border-down-line bg-down-wash'}`}>
            <div className="flex items-center gap-1.5">
              <span className={`text-[11px] font-semibold ${side === 'long' ? 'text-up-strong' : 'text-down-strong'}`}>
                {side === 'long' ? 'BUY when' : 'SELL when'}
              </span>
              <label className="ml-auto flex items-center gap-1">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 accent-[var(--ds-accent)]"
                  checked={enabled}
                  onChange={(e) => setEnabled(side, e.target.checked)}
                />
                <span className="faint text-[10px]">enabled</span>
              </label>
            </div>

            {node ? (
              <GroupEditor
                node={node}
                depth={0}
                features={features}
                binaryOps={binaryOps}
                opDocs={opDocs}
                onChange={(next) => patchSide(side, next)}
                onRemove={() => patchSide(side, null)}
              />
            ) : (
              <p className="sg-note mt-1">Disabled — {side === 'long' ? 'no long entries' : 'no short entries'} will be taken.</p>
            )}

            {problems?.[side]?.length ? (
              <div className="notice notice--warn mt-1.5">
                <span className="text-[10px]">{problems[side].join(' ')}</span>
              </div>
            ) : null}
          </div>
        );
      })}

      {mode === 'auto' && ruleSummary ? (
        <div className="sg-kvlist">
          <div className="sg-kv">
            <span className="sg-lab">BUY</span>
            <span className="sg-num">{ruleSummary.long || '—'}</span>
          </div>
          <div className="sg-kv">
            <span className="sg-lab">SELL</span>
            <span className="sg-num">{ruleSummary.short || '—'}</span>
          </div>
        </div>
      ) : null}

      {showJson ? (
        <pre className="sg-scroll max-h-56 overflow-auto rounded-md border border-border-subtle bg-surface-subtle p-2 font-mono text-[10px] text-ink-2">
          {JSON.stringify(rules, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}

/* ── Recursive group editor ─────────────────────────────────────────────── */

type GroupEditorProps = {
  node: RuleGroup;
  depth: number;
  features: string[];
  binaryOps: OperatorDoc[];
  opDocs: Map<string, OperatorDoc>;
  onChange: (node: RuleGroup) => void;
  onRemove: () => void;
};

function GroupEditor({ node, depth, features, binaryOps, opDocs, onChange, onRemove }: GroupEditorProps) {
  const children = node.conditions ?? [];

  const replaceChild = (index: number, child: RuleCondition | RuleGroup) => {
    const next = [...children];
    next[index] = child;
    onChange({ ...node, conditions: next });
  };

  const removeChild = (index: number) => {
    onChange({ ...node, conditions: children.filter((_, i) => i !== index) });
  };

  return (
    <div
      className={`mt-1.5 flex flex-col gap-1.5 ${depth > 0 ? 'rounded-md border border-border-subtle bg-surface p-1.5' : ''}`}
    >
      <div className="flex items-center gap-1.5">
        <select
          className="input w-auto py-0.5 text-[11px]"
          value={node.operator}
          aria-label="Logical operator"
          onChange={(e) => onChange({ ...node, operator: e.target.value as RuleGroup['operator'] })}
        >
          <option value="AND">ALL of (AND)</option>
          <option value="OR">ANY of (OR)</option>
          <option value="NOT">NONE of (NOT)</option>
        </select>
        <span className="faint text-[10px]">{children.length} clause{children.length === 1 ? '' : 's'}</span>
        {depth > 0 ? (
          <button type="button" className="btn-ic ml-auto" onClick={onRemove} aria-label="Remove nested group">
            <Trash2 size={11} />
          </button>
        ) : null}
      </div>

      {children.map((child, index) =>
        isGroup(child) ? (
          <GroupEditor
            key={`g-${index}`}
            node={child}
            depth={depth + 1}
            features={features}
            binaryOps={binaryOps}
            opDocs={opDocs}
            onChange={(next) => replaceChild(index, next)}
            onRemove={() => removeChild(index)}
          />
        ) : (
          <ConditionRow
            key={`c-${index}`}
            node={child}
            features={features}
            binaryOps={binaryOps}
            opDocs={opDocs}
            onChange={(next) => replaceChild(index, next)}
            onRemove={() => removeChild(index)}
          />
        ),
      )}

      <div className="flex flex-wrap items-center gap-1">
        <button
          type="button"
          className="btn btn-ic"
          onClick={() => onChange({ ...node, conditions: [...children, condition(features[0] ?? 'close', '>', 0)] })}
        >
          <Plus size={11} /> condition
        </button>
        {depth < 2 ? (
          <button
            type="button"
            className="btn btn-ic"
            onClick={() => onChange({ ...node, conditions: [...children, group('AND', [condition(features[0] ?? 'close', '>', 0)])] })}
          >
            <Plus size={11} /> group
          </button>
        ) : null}
      </div>
    </div>
  );
}

/* ── Single condition row ───────────────────────────────────────────────── */

function ConditionRow({
  node,
  features,
  binaryOps,
  opDocs,
  onChange,
  onRemove,
}: {
  node: RuleCondition;
  features: string[];
  binaryOps: OperatorDoc[];
  opDocs: Map<string, OperatorDoc>;
  onChange: (node: RuleCondition) => void;
  onRemove: () => void;
}) {
  const doc = opDocs.get(node.operator);
  const unary = UNARY.has(node.operator);
  const range = RANGE.has(node.operator) || Boolean(doc?.takes_range);
  const rightKind: 'feature' | 'value' | 'range' =
    range ? 'range' : typeof node.right === 'string' ? 'feature' : 'value';
  const rangePair: [number, number] = Array.isArray(node.right) ? node.right : [-1.5, 1.5];

  const setOperator = (operator: string) => {
    const nextDoc = opDocs.get(operator);
    const nextUnary = UNARY.has(operator);
    const nextRange = RANGE.has(operator) || Boolean(nextDoc?.takes_range);
    onChange({
      ...node,
      operator,
      right: nextUnary ? undefined : nextRange ? [-1.5, 1.5] : (node.right ?? 0),
    });
  };

  return (
    <div className="flex flex-wrap items-center gap-1">
      <select
        className="input max-w-[9.5rem] flex-1 py-0.5 text-[11px]"
        value={typeof node.left === 'string' ? node.left : ''}
        aria-label="Left operand"
        onChange={(e) => onChange({ ...node, left: e.target.value })}
      >
        {features.length === 0 ? <option value="">no features</option> : null}
        {features.map((f) => (
          <option key={f} value={f}>
            {f}
          </option>
        ))}
      </select>

      <select
        className="input w-auto py-0.5 text-[11px]"
        value={node.operator}
        aria-label="Operator"
        onChange={(e) => setOperator(e.target.value)}
      >
        {binaryOps.map((op) => (
          <option key={op.name} value={op.name} title={op.description}>
            {op.label}
          </option>
        ))}
      </select>

      {unary ? null : range ? (
        <span className="flex items-center gap-1">
          <input
            type="number"
            className="input w-16 py-0.5 text-[11px]"
            value={rangePair[0]}
            aria-label="Range low"
            onChange={(e) => onChange({ ...node, right: [Number(e.target.value) || 0, rangePair[1]] })}
          />
          <input
            type="number"
            className="input w-16 py-0.5 text-[11px]"
            value={rangePair[1]}
            aria-label="Range high"
            onChange={(e) => onChange({ ...node, right: [rangePair[0], Number(e.target.value) || 0] })}
          />
        </span>
      ) : (
        <span className="flex items-center gap-1">
          <select
            className="input w-auto py-0.5 text-[11px]"
            value={rightKind}
            aria-label="Right operand kind"
            onChange={(e) => {
              const kind = e.target.value as 'feature' | 'value';
              onChange({ ...node, right: kind === 'feature' ? (features[0] ?? 'close') : 0 });
            }}
          >
            <option value="feature">feature</option>
            <option value="value">value</option>
          </select>
          {rightKind === 'feature' ? (
            <select
              className="input max-w-[9.5rem] flex-1 py-0.5 text-[11px]"
              value={typeof node.right === 'string' ? node.right : ''}
              aria-label="Right feature"
              onChange={(e) => onChange({ ...node, right: e.target.value })}
            >
              {features.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="number"
              className="input w-20 py-0.5 text-[11px]"
              value={typeof node.right === 'number' ? node.right : 0}
              aria-label="Right value"
              onChange={(e) => onChange({ ...node, right: Number(e.target.value) || 0 })}
            />
          )}
        </span>
      )}

      <input
        type="number"
        className="input w-14 py-0.5 text-[11px]"
        value={node.bars ?? 1}
        min={1}
        aria-label="Lookback bars for this clause"
        title="Bars used by turn/slope operators"
        onChange={(e) => onChange({ ...node, bars: Math.max(1, Number(e.target.value) || 1) })}
      />

      <span className="faint max-w-[14rem] truncate text-[10px]" title={describeRule(node)}>
        {describeRule(node)}
      </span>

      <button type="button" className="btn-ic ml-auto" onClick={onRemove} aria-label="Remove condition">
        <Trash2 size={11} />
      </button>
    </div>
  );
}
