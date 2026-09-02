import type { Metadata, Viewport } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { AuthProvider } from '@/components/auth/AuthProvider';

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
  preload: false,
});

export const metadata: Metadata = {
  title: 'Droid - F&O Market Analysis',
  description: 'AI-Powered Indian F&O Market Analysis Platform',
};

export const viewport: Viewport = {
  themeColor: '#f8fafc',
  colorScheme: 'light',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable}`}>
      <body className={`${inter.className} antialiased bg-background text-foreground`}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
