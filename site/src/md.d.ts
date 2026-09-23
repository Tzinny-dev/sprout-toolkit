// Allow `import x from './file.md?raw'` (Vite's built-in raw import).
declare module '*.md?raw' {
  const content: string;
  export default content;
}
