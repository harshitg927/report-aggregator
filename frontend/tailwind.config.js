/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,jsx}",
    "./components/**/*.{js,jsx}",
    "./lib/**/*.{js,jsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "1.5rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
        background: "var(--background)",
        foreground: "var(--foreground)",
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        brand: {
          900: "#C31730",
          800: "#EC4958",
          700: "#F57B85",
          100: "#FFCED7",
        },
        tertiary1: {
          900: "#000B54",
          800: "#004494",
          600: "#4D7CB7",
          400: "#B0C4DE",
          200: "#E2EFFF",
        },
        tertiary2: {
          900: "#513DA8",
          800: "#6D67D9",
          600: "#9BA1F4",
          400: "#D3D6FF",
          200: "#EEEFFF",
        },
        neutral: {
          900: "#303030",
          800: "#616161",
          700: "#888888",
          600: "#A9A9A9",
          400: "#CECECE",
          300: "#E1E1E1",
          200: "#EDEDED",
          100: "#F6F6F6",
        },
        alert: {
          DEFAULT: "#D02216",
          hover: "#A41411",
          bg: "#FFEBEE",
        },
        error: {
          100: "#FFEBEE",
          500: "#E03C31",
          600: "#A41411",
          700: "#5F2120",
        },
        warning: {
          100: "#FFF3E0",
          500: "#AF4F00",
          600: "#EF6C00",
          700: "#663C00",
        },
        info: {
          100: "#E1F5FE",
          500: "#0079BA",
          700: "#014361",
        },
        success: {
          100: "#E8F5E9",
          500: "#2E7D32",
          700: "#1E4620",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        inter: ["Inter", "sans-serif"],
        sans: ["Inter", "sans-serif"],
      },
      fontSize: {
        base: ["14px", "20px"],
      },
      spacing: {
        page: "32px",
        gutter: "24px",
        13: "3.25rem",
        18: "4.5rem",
      },
      height: {
        13: "3.25rem",
        18: "4.5rem",
      },
    },
  },
  plugins: [],
};
