import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "./globals.css";
import { Toaster } from "sonner";
import { Header } from "@/components/header";
import { Footer } from "@/components/footer";

export const metadata = {
  title: "FOSSology Report Aggregator",
  description: "Merge and transparently edit FOSSology reports.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col bg-background font-inter antialiased">
        <Header />
        <main className="flex-grow px-page py-6">{children}</main>
        <Footer />
        <Toaster richColors closeButton position="top-right" />
      </body>
    </html>
  );
}
