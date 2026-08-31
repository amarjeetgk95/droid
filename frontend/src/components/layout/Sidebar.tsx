import { LayoutDashboard, TrendingUp, BarChart3, Grid3X3, Target, Search, Brain, History, FileText, Bell, Star, Settings, Coins, LineChart, Database, Cpu } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export function Sidebar() {
  const pathname = usePathname();

  const links = [
    { href: '/', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/markets', label: 'Markets', icon: TrendingUp },
    { href: '/crypto', label: 'Crypto (Binance)', icon: Coins },
    { href: '/futures', label: 'Futures', icon: BarChart3 },
    { href: '/options', label: 'Options', icon: Grid3X3 },
    { href: '/chart-analysis', label: 'Chart Forecast', icon: LineChart },
    { href: '/historical-intelligence', label: 'Historical Intelligence', icon: Database },
    { href: '/strategy', label: 'Strategy', icon: Target },
    { href: '/scanner', label: 'Scanner', icon: Search },
    { href: '/ai-analysis', label: 'AI Analysis', icon: Brain },
    { href: '/backtesting', label: 'Backtesting', icon: History },
    { href: '/paper-trading', label: 'Paper Trading', icon: FileText },
    { href: '/algo-trading', label: 'Algo Trading', icon: Cpu },
    { href: '/alerts', label: 'Alerts', icon: Bell },
    { href: '/watchlist', label: 'Watchlist', icon: Star },
    { href: '/settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside className="w-64 border-r border-border bg-card flex flex-col hidden md:flex">
      <div className="h-14 flex items-center px-4 border-b border-border shrink-0">
        <h1 className="text-xl font-bold tracking-tight text-primary flex items-center gap-2">
          <span className="bg-primary text-primary-foreground p-1 rounded">D</span>
          DROID
        </h1>
        <span className="ml-auto text-xs bg-muted text-muted-foreground px-2 py-1 rounded-full font-medium">Phase 1</span>
      </div>
      <nav className="flex-1 overflow-y-auto p-4 space-y-1">
        {links.map((link) => {
          const isActive = pathname === link.href;
          const Icon = link.icon;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${isActive ? 'bg-secondary text-primary' : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground'}`}
            >
              <Icon className="w-4 h-4" />
              {link.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
