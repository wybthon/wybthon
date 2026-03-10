# CHANGELOG


## v0.12.0 (2026-03-10)

### Features

- **component**: Add @component decorator for Pythonic kwarg props
  ([`ad84570`](https://github.com/wybthon/wybthon/commit/ad84570f873a7e0de83c90be6342201361c2f04b))


## v0.11.0 (2026-03-06)

### Features

- **vdom,component,hooks**: Add core React primitives
  ([`fd8d4bb`](https://github.com/wybthon/wybthon/commit/fd8d4bbd52664b75ccac8ab9dd5fcd910cb5464b))


## v0.10.0 (2026-03-05)

### Continuous Integration

- **workflows**: Append detailed changes link to release notes
  ([`8ce7e28`](https://github.com/wybthon/wybthon/commit/8ce7e28be9e14d0770c59b0114bd882620ab0361))

- **workflows**: Fix duplicate release, and use changelog for release notes
  ([`2cbdaa7`](https://github.com/wybthon/wybthon/commit/2cbdaa7db3c50368ece3a94ed3a2f51d14098e8a))

- **workflows**: Simplify release pipeline to use python-semantic-release defaults
  ([`da1dfee`](https://github.com/wybthon/wybthon/commit/da1dfee68cc2bb28670d0d6cf71c58b59514300e))

### Features

- **html**: Add Pythonic element helpers and Fragment; remove BaseComponent
  ([`5ce94d5`](https://github.com/wybthon/wybthon/commit/5ce94d54b7846a9a8b1297e1cadd2f001b416083))


## v0.9.0 (2026-03-05)

### Continuous Integration

- **workflows**: Add semantic-release pipeline and PR commit linting
  ([`ef27399`](https://github.com/wybthon/wybthon/commit/ef27399462e6e2e87bd36264ea2b4a73d02a8a25))

- **workflows**: Decouple PyPI publish from release creation
  ([`f1c07a9`](https://github.com/wybthon/wybthon/commit/f1c07a935161703e45bcd5b06b9d09b1b17dd9a5))

### Documentation

- **mkdocs**: Remove roadmap document
  ([`1868f86`](https://github.com/wybthon/wybthon/commit/1868f86547f8bc0fd1c6b6192609c5b47340ce3c))

- **repo**: Add badges to README
  ([`0844113`](https://github.com/wybthon/wybthon/commit/08441137e8d315113e4d6c7582105f10fc816d57))

- **repo**: Simplify README to single-paragraph intro, and link docs site
  ([`4c600b1`](https://github.com/wybthon/wybthon/commit/4c600b1b5b0668d6fb4422b520f46dd9c099f69a))

### Features

- **hooks**: Add React-style hooks for stateful function components
  ([`ccec066`](https://github.com/wybthon/wybthon/commit/ccec0668d5732d9db49732690bfc4e26042d8e37))


## v0.8.0 (2025-10-22)

### Chores

- **pyproject,package**: Bump version to 0.8.0
  ([`d5f633d`](https://github.com/wybthon/wybthon/commit/d5f633d76d382ec25d5813f5ab15497c3cbf8adf))

### Code Style

- Format code with Black
  ([`7b3dbcf`](https://github.com/wybthon/wybthon/commit/7b3dbcfc564b43c9c1c040569abadeab896909fa))

### Documentation

- **package**: Add one-line docstrings across public API
  ([`234632e`](https://github.com/wybthon/wybthon/commit/234632e65f01784c792cb6ad277f77bb7dbbff92))

### Features

- **forms,tests,mkdocs**: Add rules_from_schema for schema-based validation
  ([`f7152fe`](https://github.com/wybthon/wybthon/commit/f7152fed8af1edcd9c6578ddc00e8e4e014a71fd))

- **router,mkdocs,examples**: Forward Link props; complete event docs
  ([`b72c96b`](https://github.com/wybthon/wybthon/commit/b72c96b97d959ca7aaeba00018018880948df5d9))


## v0.7.0 (2025-10-13)

### Chores

- **pyproject,package**: Bump version to 0.7.0
  ([`50069dd`](https://github.com/wybthon/wybthon/commit/50069dd3566944319f5777549fbfe7e9fd96d2a6))

### Continuous Integration

- **workflows,mkdocs**: Collect coverage via package; avoid artifact conflicts
  ([`6fd1352`](https://github.com/wybthon/wybthon/commit/6fd1352128e7864e5da54ef756e2758b5233dbcf))

- **workflows,pyproject,mkdocs**: Add coverage gate (45%); upload coverage.xml
  ([`d1787fa`](https://github.com/wybthon/wybthon/commit/d1787fac4fdd560e7d02affa065f54e4b9dc4c20))

### Documentation

- **mkdocs,examples**: Add Patterns demo and expand authoring patterns
  ([`0a58825`](https://github.com/wybthon/wybthon/commit/0a58825001e8b25fb3279c91b77b964934f8c470))

### Features

- **package**: Export Resource and FieldState at top level
  ([`03f93ab`](https://github.com/wybthon/wybthon/commit/03f93ab44d827733163537d2b7f21d64623a6a0b))

### Refactoring

- **package,mkdocs**: Finalize public API via __all__; improve typing
  ([`40c5b2a`](https://github.com/wybthon/wybthon/commit/40c5b2aa7017f82fbc8d8a21afed05aff675f440))

- **reactivity**: Move __all__ to top
  ([`28a646e`](https://github.com/wybthon/wybthon/commit/28a646ea4ab5e56ffe7f8e6ac006b3ff96165ce3))


## v0.6.0 (2025-10-12)

### Bug Fixes

- **dev**: Use ThreadingMixIn so SSE does not block other requests
  ([`1eba8b3`](https://github.com/wybthon/wybthon/commit/1eba8b3bfa7fb7dcbec95f8cc287d1d30082d75b))

### Chores

- **pyproject,package**: Bump version to 0.6.0
  ([`ae279f3`](https://github.com/wybthon/wybthon/commit/ae279f35220fc3e2563492ad8b24a0f43076265d))

### Documentation

- **mkdocs**: Add advanced usage and troubleshooting to dev server guide
  ([`f9729fa`](https://github.com/wybthon/wybthon/commit/f9729fa5a4039475da4386822538dce5d70fa00e))

### Features

- **dev**: Static mounts, auto-open, and demo error overlay
  ([`47a9f7c`](https://github.com/wybthon/wybthon/commit/47a9f7c208a45f4bd47445fd8b6bd2b6cec9e52f))

- **dev,examples,mkdocs**: Add cache busting and improve startup messages
  ([`774315e`](https://github.com/wybthon/wybthon/commit/774315eb74983a9333bae9c0780ba3ed1fd0ddd1))


## v0.5.0 (2025-10-09)

### Bug Fixes

- **vdom,tests,bench**: Correct keyed reorder diff with LIS
  ([`ba4f5fd`](https://github.com/wybthon/wybthon/commit/ba4f5fdcd550c473f5ee3ddb54dac412ac87f2ed))

### Chores

- **pyproject,package**: Bump version to 0.5.0
  ([`34d9e02`](https://github.com/wybthon/wybthon/commit/34d9e022532d954f75cf41d1bce9b3842bff7d58))

### Documentation

- **mkdocs**: Set social card text color to white
  ([`e147d9c`](https://github.com/wybthon/wybthon/commit/e147d9c7e97067c2f0f65d95a5bdd1dd36fa8340))

### Testing

- **vdom**: Add prop edge-case tests for style/dataset/value/checked
  ([`4bf308f`](https://github.com/wybthon/wybthon/commit/4bf308f7f898fee5edbbaf3f005f177016071b22))

- **vdom**: Add text-node fast-path and unkeyed text reorder tests
  ([`b06a950`](https://github.com/wybthon/wybthon/commit/b06a950420cf68c761d6f08cb03326138d5f1a9b))


## v0.4.0 (2025-10-08)

### Chores

- **pyproject,package,mkdocs**: Bump version to 0.4.0
  ([`b205d3d`](https://github.com/wybthon/wybthon/commit/b205d3d78cf667286b7aad8c7be939a42720493a))

### Features

- **events**: Teardown delegated root listeners when no handlers remain
  ([`2a95430`](https://github.com/wybthon/wybthon/commit/2a95430a5ba358b3e2b9a0101194a12a10d2dbf9))

- **forms**: Aggregated submit validation and a11y helpers
  ([`5a92039`](https://github.com/wybthon/wybthon/commit/5a9203975a3ee8d9abd51d10cea5cece73ad990c))

- **vdom**: Errorboundary reset keys and on_error
  ([`9c2fbb7`](https://github.com/wybthon/wybthon/commit/9c2fbb7d3e98a38a1c543bf7859d8f2d5cf7a142))


## v0.3.0 (2025-10-07)

### Chores

- **pyproject,package,mkdocs**: Bump version to 0.3.0
  ([`c4f6258`](https://github.com/wybthon/wybthon/commit/c4f62588f4141eeeba5509eb51871356964fb5dc))

### Documentation

- **mkdocs**: Correct mkdocstrings directive in vdom API page
  ([`ba594f4`](https://github.com/wybthon/wybthon/commit/ba594f4e62beddc7c51ee2c37d64d46c4b19f689))

- **mkdocs**: Fix mkdocstrings directive in api/wybthon.md
  ([`65a883a`](https://github.com/wybthon/wybthon/commit/65a883aa418304fcc06b7fd78c6bde46796db918))

### Features

- **examples**: Split demo routes with lazy(); add hover preload
  ([`ddcafd5`](https://github.com/wybthon/wybthon/commit/ddcafd51582c9f5967ed6d0e615a11e94b3f446f))

- **lazy,mkdocs,tests**: Add lazy-loading utilities and exports
  ([`10778ce`](https://github.com/wybthon/wybthon/commit/10778ce172571a599761892096f8023e06d9113c))

- **vdom,package**: Add Suspense for resource loading fallbacks
  ([`34b4bf0`](https://github.com/wybthon/wybthon/commit/34b4bf0b230e587b3c2194afc3f3295a46b481e4))


## v0.2.0 (2025-10-06)

### Bug Fixes

- **examples**: Compute base_path and pass to Router/Link in demo
  ([`2063275`](https://github.com/wybthon/wybthon/commit/2063275270d80ca2bd4eb9e498034dad0470851d))

- **vdom,examples**: Correct Provider patch; bundle router_core in demo
  ([`8cfde64`](https://github.com/wybthon/wybthon/commit/8cfde649566d88d0f8bd78426d8c141965ebbdea))

### Chores

- **pyproject,package**: Bump version to 0.2.0
  ([`8cb9a98`](https://github.com/wybthon/wybthon/commit/8cb9a98063a99cdadf9a2d399a60c73331e5a484))

### Features

- **router**: Add Link active class and replace navigation
  ([`e6ae797`](https://github.com/wybthon/wybthon/commit/e6ae7977f39d4b267115cd0cebfc4c5397efee7e))

- **router,examples,mkdocs**: Nested routes, wildcard, base path, 404
  ([`43d170c`](https://github.com/wybthon/wybthon/commit/43d170c88636cd7b6c90b43e13f3dae97e3d8ec6))


## v0.1.1 (2025-10-03)

### Bug Fixes

- **events**: Allow import outside browser; document DomEvent; add tests
  ([`a6019e5`](https://github.com/wybthon/wybthon/commit/a6019e5d8015f9f34a519e13830d83c23701cf29))

- **reactivity,vdom**: Deterministic flush; dispose cancels; props fixes
  ([`ae37d63`](https://github.com/wybthon/wybthon/commit/ae37d637e053f9ed26865ac395d5c8aef5a51e8b))

### Chores

- **pyproject,package**: Bump version to 0.1.1
  ([`ae10355`](https://github.com/wybthon/wybthon/commit/ae1035539ee35fedbe378ddfe89d37906ab41224))

### Continuous Integration

- **workflows**: Add Playwright-based Pyodide smoke test in CI
  ([`3d5a2b7`](https://github.com/wybthon/wybthon/commit/3d5a2b713d66ffd747e1ffbc22e5a3cf83bd62d4))

### Documentation

- **mkdocs**: Add 2rem bottom spacing after hiding footer
  ([`3e82dbd`](https://github.com/wybthon/wybthon/commit/3e82dbd2cab71d31416c7a4a5a33105d3c2b8b44))

- **mkdocs**: Add authoring patterns guide and update related docs
  ([`dd0b9c7`](https://github.com/wybthon/wybthon/commit/dd0b9c7e7409b9f16605dae810ac1f7fade2a5d6))

- **mkdocs**: Add versioned roadmap, SemVer policy; drop TODO.md
  ([`1045df3`](https://github.com/wybthon/wybthon/commit/1045df379c1596324f3c71d569423715f1f71c3e))

- **mkdocs**: Document release branching strategy for major versions
  ([`29af14f`](https://github.com/wybthon/wybthon/commit/29af14f8ed7789add629b1c88c5f5be74710bb93))

- **mkdocs**: Revamp docs site, scaffold content, and brand styling
  ([`9a54b36`](https://github.com/wybthon/wybthon/commit/9a54b3648521f708e55232d52ae365190ee05274))

- **repo**: Add repo_url to mkdocs.yml to show GitHub link in header
  ([`e349abe`](https://github.com/wybthon/wybthon/commit/e349abe7806a622fbe30bcf1634bddde359ff893))


## v0.1.0 (2025-10-01)

### Bug Fixes

- **reactivity,vdom,package**: Make CI pass
  ([`57a4d63`](https://github.com/wybthon/wybthon/commit/57a4d63ca02c30afe56fe9299f6ffdff87160be0))

### Build System

- **pyproject,workflows**: Add dev/ci extras; drop requirements.txt
  ([`321d920`](https://github.com/wybthon/wybthon/commit/321d920c15348ac71cc5d36c363013ac2897ce5f))

- **repo,pyproject**: Enable Material social cards; add imaging extras
  ([`73db44d`](https://github.com/wybthon/wybthon/commit/73db44d504fd0f09d6cb8defca874643d6a79aed))

### Continuous Integration

- **workflows**: Configure docs custom domain docs.wybthon.com
  ([`cb10611`](https://github.com/wybthon/wybthon/commit/cb1061103bf97dc48012f64a58be2b558f3de766))

- **workflows,pyproject,repo**: Add PyPI release workflow and prep 0.1.0
  ([`e29f4ea`](https://github.com/wybthon/wybthon/commit/e29f4ea2b8eb069cfb38b1abaf2e9f2de3308dc0))

### Documentation

- **repo**: Update CONTRIBUTING with single-main release workflow
  ([`f81abd7`](https://github.com/wybthon/wybthon/commit/f81abd74f10e47ee7bc7e852a271399fb6b98ab5))

- **repo**: Update README project structure; remove future plans
  ([`b993e75`](https://github.com/wybthon/wybthon/commit/b993e752480b61fa588fa28b061f5aee910dda13))

### Features

- Add composability
  ([`a62a8b0`](https://github.com/wybthon/wybthon/commit/a62a8b0197c1b6ba5c0be83e1bcbe49f54b20780))

- Add HTML templating
  ([`7f4610f`](https://github.com/wybthon/wybthon/commit/7f4610fce9c901736fc9235fc5eb38eb97e4d49b))

- Update README
  ([`9b1072d`](https://github.com/wybthon/wybthon/commit/9b1072d1405b67eb83a50147f880d3e4e53656be))

- **examples**: Switch demo to app/ with file-based pages and layout
  ([`e90aa14`](https://github.com/wybthon/wybthon/commit/e90aa1491b4597055597145f41536faf931f5a30))

- **vdom,component,router**: Add VDOM, signals, context, router; pkg restructure
  ([`a62e08c`](https://github.com/wybthon/wybthon/commit/a62e08cb8c5622d0b42d5a1ee97584ac9144ebe5))

- Implement VNode/h()/render(), keyed diff, text updates - Add class/function components with
  lifecycle and cleanup - Introduce signals/computed/effect/batch with microtask scheduler - Event
  delegation with DomEvent and centralized handlers - Context API
  (create_context/use_context/Provider) - Router (Router/Route/Link, navigate, popstate) -
  Restructure to src/ layout; move demo to examples/demo; add pyproject - Update demo to showcase
  VDOM, signals, context, and router

BREAKING CHANGE: repository moved to src/wybthon; legacy apps/ and libs/ removed; demo paths
  changed.

- **vdom,dev,forms**: Forms, async resource, error boundaries, dev server, docs+CI
  ([`feaa2b4`](https://github.com/wybthon/wybthon/commit/feaa2b4f86a7837701ffbed9e1d640282ad6b330))

### Performance Improvements

- **vdom**: Implement keyed children reordering with minimal DOM moves
  ([`0fa54c5`](https://github.com/wybthon/wybthon/commit/0fa54c5baed2ef76752cb549ddda11e370d580dc))
