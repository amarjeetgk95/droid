import EventDetailClient from './EventDetailClient';

export async function generateStaticParams() {
  return [
    { eventId: 'RBI_MPC_20261009' },
    { eventId: 'RBI_MPC_20261204' },
    { eventId: 'RBI_MPC_20270205' },
    { eventId: 'NSE_CORP_INFY_20261015' },
    { eventId: 'NSE_CORP_RELIANCE_20261017' },
    { eventId: 'NSE_CORP_HDFCBANK_20261019' },
    { eventId: 'SEBI_CIRC_20261002' },
  ];
}

export default async function EventDetailPage({ params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;
  return <EventDetailClient eventId={eventId} />;
}
