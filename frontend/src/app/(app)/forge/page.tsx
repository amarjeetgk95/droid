import { permanentRedirect } from 'next/navigation';

/** Signal Forge has been consolidated into the Signals desk (scanner tab). */
export default function SignalForgePage() {
  permanentRedirect('/signals?tab=scanner');
}
