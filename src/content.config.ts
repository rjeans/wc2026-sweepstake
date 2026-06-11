import { defineCollection, z } from 'astro:content';

const recaps = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    pubDate: z.date(),
    summary: z.string().optional(),
  }),
});

export const collections = { recaps };
