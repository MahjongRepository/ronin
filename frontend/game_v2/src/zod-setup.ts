import { en } from "zod/locales";
import { z } from "zod/mini";

z.config({ ...en(), jitless: true });
