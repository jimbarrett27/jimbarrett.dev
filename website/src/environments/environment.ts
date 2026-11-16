/**
 * Development environment. Replaced at build time for production
 * (see environment.prod.ts + angular.json fileReplacements).
 */
export const environment = {
  production: false,
  // Public GCS bucket the telegram_bot tapestry job writes to. Same URL in dev
  // and prod: the objects are public-read and the bucket allows cross-origin GET.
  tapestryBucketBase: 'https://storage.googleapis.com/personal-website-318015-tapestry/tapestry',
};
