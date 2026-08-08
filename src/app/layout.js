import './globals.css';
import { Footer, TopBar } from '../components/Chrome';

export const metadata = {
  title: 'Structura — structuring engine for energy project finance',
  description:
    'Describe a project in six fields. Structura resolves the rest from comparable transactions and cited market bands, screens every capital structure, and shows the economics by party — with every number badged as stated, benchmark, assumed, or not disclosed.',
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
