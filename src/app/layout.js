import './globals.css';
import { Footer, TopBar } from '../components/Chrome';

export const metadata = {
  title: 'Structura — current-law structuring engine for energy project finance',
  description:
    'Put in a project, get back sized debt, the full cash waterfall, and a side-by-side comparison of every 2026 capital structure — with a lender-grade Excel model. Free and open source.',
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#0a0d12',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <TopBar />
        <div className="shell">
          {children}
          <Footer />
        </div>
      </body>
    </html>
  );
}
