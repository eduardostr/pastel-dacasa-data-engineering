# Configuração segura

Projeto de portfólio local, com dados fictícios. Não é um serviço pronto para exposição pública em produção.

- Copie `.env.example` para `.env` apenas se não existir e defina uma senha local própria. Backend e ETL rejeitam ausência/placeholder; Compose exige POSTGRES_PASSWORD. ETL_DATABASE_URL explícita permanece disponível como alternativa.
- Nunca versione `.env`, tokens, chaves, backups, dumps ou dados operacionais. Ignore não remove arquivos já commitados: revise o staging antes de publicar.
- PostgreSQL usa bind de loopback no Compose. Execute API, Streamlit e Prefect em loopback conforme os guias. Não exponha endpoints administrativos sem controles próprios de produção.
- Não há dados de acesso em `.env.example`. Fixtures de testes contêm apenas valores demonstrativos e domínios de exemplo/teste.
- A autoria e a licença MIT identificam o titular. O uso público do e-mail de autoria foi aceito pelo titular.
- Dependências por intervalo não são lockfile por hash; não foi feita certificação de segurança de dependências. Use scanners e atualizações revisadas antes de implantação real.

Este repositório nasce de uma seleção explícita de arquivos, com um novo histórico Git. Não recebe objetos, refs, PRs, caches ou assets do repositório anterior. Isso não afirma remoção de cópias antigas mantidas em outros locais.
