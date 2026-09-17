'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { classifyDirection, type AutoDetectCandidate } from '@/lib/api/signals';
import { SignalBuilder } from './SignalBuilder';
import { AIConfirmationPanel } from './AIConfirmationPanel';
import { MLGateIndicator } from './MLGateIndicator';
import { TelegramPreview } from './TelegramPreview';
import { ExpectedMoveProjection } from './ExpectedMoveProjection';
import { ContractSelector, type ContractSelectionSummary } from './ContractSelector';
import { PathSimulator } from './PathSimulator';
import { ConfluenceBreakdown } from './ConfluenceBreakdown';
import { ValidationGateway } from './ValidationGateway';
import { useForgeMarket } from './useForgeMarket';
import { emptyForgeForm, finiteNumber } from './forgeLogic';

export const ForgeWorkbench: React.FC = () => {
  const { instrument } = useInstrument();
  const market = useForgeMarket(instrument);
  const [formData, setFormData] = useState<Record<string, unknown>>(() => emptyForgeForm(instrument));
  const [candidate, setCandidate] = useState<AutoDetectCandidate | null>(null);
  const [candidateDetected, setCandidateDetected] = useState<boolean | null>(null);
  const [contract, setContract] = useState<ContractSelectionSummary | null>(null);

  // Instrument switch resets the whole forge: stale levels from another index
  // must never survive into the new instrument's form or payload.
  useEffect(() => {
    setFormData(emptyForgeForm(instrument));
    setCandidate(null);
    setCandidateDetected(null);
    setContract(null);
  }, [instrument]);

  const handleFormChange = useCallback((data: Record<string, unknown>) => {
    setFormData((prev) => ({ ...prev, ...data }));
  }, []);

  const handleCandidate = useCallback((next: AutoDetectCandidate | null, detected: boolean) => {
    setCandidate(next);
    setCandidateDetected(detected);
  }, []);

  const handleSelectionChange = useCallback((selection: ContractSelectionSummary | null) => {
    setContract(selection);
  }, []);

  const direction = classifyDirection(
    typeof formData.direction === 'string' ? formData.direction : 'CALL',
  );
  const stop = finiteNumber(formData.stop_loss);
  const target = finiteNumber(formData.target_2) ?? finiteNumber(formData.target_1);

  return (
    <div className="space-y-5">
      {/* ML Shadow Gate Top Alert */}
      <MLGateIndicator />

      {/* Main 2-Column Grid: Builder on Left, Quantitative & AI Verification on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left Column: Signal Builder & Derivatives Selector (7 cols) */}
        <div className="lg:col-span-7 space-y-5">
          <SignalBuilder
            key={instrument}
            underlying={instrument}
            onFormChange={handleFormChange}
            onCandidate={handleCandidate}
          />
          <ContractSelector
            underlying={instrument}
            direction={direction}
            spot={market.spot}
            iv={market.iv}
            marketError={market.error}
            onSelectionChange={handleSelectionChange}
          />
          <PathSimulator
            key={instrument}
            underlying={instrument}
            spot={market.spot}
            iv={market.iv}
            dteDays={market.dteDays}
            atmStrike={market.atmStrike}
            direction={direction}
            stop={stop}
            target={target}
            quantity={contract?.lotSize ?? null}
            marketError={market.error}
          />
        </div>

        {/* Right Column: AI Validation, Confluence, Telegram Preview (5 cols) */}
        <div className="lg:col-span-5 space-y-5">
          <AIConfirmationPanel key={instrument} payload={formData} />
          <ConfluenceBreakdown candidate={candidate} detected={candidateDetected ?? undefined} />
          <ExpectedMoveProjection
            underlying={instrument}
            spot={market.spot}
            iv={market.iv}
            direction={direction}
            structuralTarget={target}
            marketError={market.error}
          />
          <TelegramPreview payload={formData} />
          <ValidationGateway />
        </div>
      </div>
    </div>
  );
};
