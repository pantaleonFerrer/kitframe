import type { Metadata } from "next";
import { Inter, Lora } from "next/font/google";
import { Providers } from "@/components/providers";
import { AuthProvider } from "@/hooks/use-auth";
import { LocaleSync } from "@/components/LocaleSync";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const lora = Lora({
  variable: "--font-lora",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Kitframe",
  description: "Product digitization and creative workflow by Gathered",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className={`${inter.variable} ${lora.variable} h-full antialiased`}>
      <body className="min-h-full font-sans">
        <Providers>
          <AuthProvider>
            <LocaleSync />
            <TooltipProvider delayDuration={200}>
              {children}
              <Toaster />
            </TooltipProvider>
          </AuthProvider>
        </Providers>
      </body>
    </html>
  );
}
