import type { Metadata, Viewport } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { AuthProvider } from '@/components/auth/AuthProvider';
import { ThemeSync } from '@/components/ThemeSync';

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
  colorScheme: 'light dark',
  width: 'device-width',
  initialScale: 1,
};

const themeInit = `(function(){try{var v2=localStorage.getItem('droid_app_settings_v2');var v1=localStorage.getItem('droid_app_settings_v1');var t=null;if(v2){try{t=JSON.parse(v2).preferences.theme}catch{}}if(!t&&v1){try{t=JSON.parse(v1).preferences.theme}catch{}}var r=t==='dark'||t==='light'?t:(t==='system'||!t)&&(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');if(!r)r='light';document.documentElement.setAttribute('data-theme',r);document.documentElement.style.colorScheme=r;document.documentElement.classList.toggle('dark',r==='dark');}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body className={`${inter.className} antialiased bg-background text-foreground`}>
        <ThemeSync />
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
