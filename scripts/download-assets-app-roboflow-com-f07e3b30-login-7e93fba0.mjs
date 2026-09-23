import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

const targets = [
  ['https://app.roboflow.com/images/cv-reel-poster.jpg', 'web/sites/app-roboflow-com-f07e3b30/login-7e93fba0/cv-reel-poster.jpg'],
  ['https://app.roboflow.com/videos/cv-reel.mp4', 'web/sites/app-roboflow-com-f07e3b30/login-7e93fba0/cv-reel.mp4'],
  ['https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg', 'web/sites/app-roboflow-com-f07e3b30/login-7e93fba0/google.svg'],
  ['https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/github.svg', 'web/sites/app-roboflow-com-f07e3b30/login-7e93fba0/github.svg'],
  ['https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/mail.svg', 'web/sites/app-roboflow-com-f07e3b30/login-7e93fba0/mail.svg'],
];

await Promise.all(targets.map(async ([url, output]) => {
  const destination = resolve(output);
  await mkdir(dirname(destination), { recursive: true });
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  await writeFile(destination, Buffer.from(await response.arrayBuffer()));
  console.log(`${url} -> ${output}`);
}));
