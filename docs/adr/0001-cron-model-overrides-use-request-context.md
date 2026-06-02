# Cron Model Overrides Use Request Context

Cron jobs may pin an execution model without changing the tenant default model. We will pass that model choice through a request-scoped context variable during the scheduled run, and `create_model_and_formatter()` will prefer the scoped override before reading the tenant default. This avoids mutating `ProviderManager.active_model`, keeps concurrent scheduled runs and normal chat requests isolated, and preserves execution-time default-model resolution when no override is present.
