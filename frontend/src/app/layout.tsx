import './globals.css';

export const metadata = {
  title: 'Sports Card Intelligence MVP',
  description: 'Personal sports card intelligence platform',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
