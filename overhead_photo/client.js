import { render } from '/plugins/overhead_core/static/overhead.js';

export default async function (shadow, ctx) {
  await render(shadow, ctx, 'photo');
}
