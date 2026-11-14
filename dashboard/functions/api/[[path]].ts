import { handle, type Env } from '../../server/annotations';
export const onRequest: PagesFunction<Env> = context => handle(context.request,context.env);
