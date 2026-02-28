// Disable Zod's JIT compilation (new Function()) to comply with CSP script-src 'self'.
// This module must be imported BEFORE any Zod schemas are created.
import { z } from "zod";

z.config({ jitless: true });
