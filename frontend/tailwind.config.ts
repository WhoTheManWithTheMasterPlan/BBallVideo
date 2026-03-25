import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        court: {
          wood: "#C8A165",
          line: "#FFFFFF",
          paint: "#E8D5B7",
        },
      },
    },
  },
  plugins: [],
};

export default config;
