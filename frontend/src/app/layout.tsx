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
  themeColor: '#ffffff',
  colorScheme: 'light',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable}`}>
      <body className="bg-background text-foreground">
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
