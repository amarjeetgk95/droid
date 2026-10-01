import type { Metadata, Viewport } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { AuthProvider } from '@/components/auth/AuthProvider';
import { WebVitalsReporter } from '@/components/common/WebVitalsReporter';
import { ToastProvider } from '@/components/ui/toast';
import { AppStreamProvider } from '@/context/AppStreamContext';
import { MarketTicksProvider } from '@/context/MarketTicksContext';
import { InstrumentProvider } from '@/context/InstrumentContext';
import { MarketSessionProvider } from '@/context/MarketSessionContext';
import { DISPLAY_BOOTSTRAP_SCRIPT } from '@/lib/displayMode';

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
  preload: true,
  fallback: ['system-ui', '-apple-system', 'sans-serif'],
});

const jetbrains = JetBrains_Mono({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-jetbrains',
  preload: true,
  fallback: ['ui-monospace', 'Consolas', 'monospace'],
});

export const metadata: Metadata = {
  title: 'Droid — F&O Terminal',
  description: 'Multi-horizon market forecast, signal generation and paper P&L for Indian F&O.',
};

export const viewport: Viewport = {
  // Mirrors --ds-page. The bootstrap script rewrites this to the dark page
  // colour when the stored display mode is the dark terminal.
  themeColor: '#f7f8fa',
  // Light is the CSS default (`:root { color-scheme: light }`); the dark theme
  // sets `color-scheme: dark`, which is what native scrollbars follow.
  colorScheme: 'light',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable}`} suppressHydrationWarning>
      <body className="bg-background text-foreground">
        {/* Appearance axes (theme / density / contrast) are stored per device
            and applied to <html> here, before the desk paints, so a dark or
            dense preference cannot flash the light comfortable default. */}
        <script dangerouslySetInnerHTML={{ __html: DISPLAY_BOOTSTRAP_SCRIPT }} />
        <WebVitalsReporter />
        <ToastProvider>
          <AuthProvider>
            <MarketSessionProvider>
              <InstrumentProvider>
                <AppStreamProvider>
                  <MarketTicksProvider>{children}</MarketTicksProvider>
                </AppStreamProvider>
              </InstrumentProvider>
            </MarketSessionProvider>
          </AuthProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
