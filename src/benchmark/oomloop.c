/* oomloop.c - fail the Nth SQLite allocation, for N = 1, 2, 3 ..., and report which N crash.
 *
 * Build against the pinned amalgamation (sqlite3.c / sqlite3.h from the 3.30.1 tree):
 *   cc -g -O1 -fsanitize=address,undefined -fno-omit-frame-pointer -I. oomloop.c sqlite3.c -o oomloop -lpthread -ldl -lm
 * Run:
 *   ASAN_OPTIONS=exitcode=86 UBSAN_OPTIONS=halt_on_error=1:exitcode=87:print_stacktrace=1 ./oomloop bug.sql
 *   ./oomloop bug.sql [maxN] [persistent]     persistent=1: allocation N AND every later one fails
 *   OOM_NOLOOKASIDE=1 ./oomloop bug.sql       turn lookaside off, so every allocation reaches the allocator
 *
 * Each N runs in its own forked child (a fresh process, so sqlite3_config() is legal every time and a crash
 * only ends that child). The child exits 100 when N is larger than the number of allocations the SQL makes:
 * that is the end of the loop.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#include "sqlite3.h"

static long g_count, g_fail_at;
static int g_persistent, g_injected;

#define HDR 16                                   /* keeps 16-byte alignment, stores the block size */
static int hit(void) {                           /* count one allocation; true if this one must fail */
  g_count++;
  if (g_count == g_fail_at || (g_persistent && g_fail_at && g_count > g_fail_at)) { g_injected = 1; return 1; }
  return 0;
}
static void *xMalloc(int n) {
  char *p; if (hit()) return 0;
  p = malloc((size_t)n + HDR); if (!p) return 0;
  *(int *)p = n; return p + HDR;
}
static void xFree(void *p) { if (p) free((char *)p - HDR); }
static void *xRealloc(void *p, int n) {
  char *q; if (hit()) return 0;
  q = malloc((size_t)n + HDR); if (!q) return 0;
  *(int *)q = n;
  if (p) { int old = *(int *)((char *)p - HDR); memcpy(q + HDR, p, old < n ? old : n); free((char *)p - HDR); }
  return q + HDR;
}
static int xSize(void *p) { return p ? *(int *)((char *)p - HDR) : 0; }
static int xRoundup(int n) { return (n + 7) & ~7; }
static int xInit(void *a) { (void)a; return 0; }
static void xShutdown(void *a) { (void)a; }

static char *slurp(const char *path) {
  FILE *f = fopen(path, "rb"); long n; char *s;
  if (!f) { perror(path); exit(2); }
  fseek(f, 0, SEEK_END); n = ftell(f); rewind(f);
  s = malloc((size_t)n + 1); if (fread(s, 1, (size_t)n, f) != (size_t)n) exit(2);
  s[n] = 0; fclose(f); return s;
}

static int child(const char *sql) {              /* one run with allocation g_fail_at failing */
  static sqlite3_mem_methods m = { xMalloc, xFree, xRealloc, xSize, xRoundup, xInit, xShutdown, 0 };
  sqlite3 *db = 0; char *err = 0; int rc;
  sqlite3_config(SQLITE_CONFIG_MALLOC, &m);
  if (getenv("OOM_NOLOOKASIDE")) sqlite3_config(SQLITE_CONFIG_LOOKASIDE, 0, 0);
  rc = sqlite3_open(":memory:", &db);
  if (rc == SQLITE_OK) rc = sqlite3_exec(db, sql, 0, 0, &err);
#ifdef SELFTEST                                   /* proves the parent detects a crash: -DSELFTEST, crash when N==3 */
  if (g_fail_at == 3) abort();
#endif
  fprintf(stderr, "N=%ld: sqlite rc=%d%s%s\n", g_fail_at, rc, err ? " " : "", err ? err : "");
  sqlite3_free(err); sqlite3_close(db); sqlite3_shutdown();
  return g_injected ? 0 : 100;                    /* 100 = the failure never triggered: N is past the end */
}

int main(int argc, char **argv) {
  long maxN = argc > 2 ? atol(argv[2]) : 100000, n, crashes = 0;
  char *sql;
  if (argc < 2) { fprintf(stderr, "usage: %s file.sql [maxN] [persistent]\n", argv[0]); return 2; }
  g_persistent = argc > 3 && atoi(argv[3]);
  sql = slurp(argv[1]);
  for (n = 1; n <= maxN; n++) {
    int st; pid_t pid; fflush(NULL);
    pid = fork();
    if (pid == 0) { g_fail_at = n; _exit(child(sql)); }
    waitpid(pid, &st, 0);
    if (WIFEXITED(st) && WEXITSTATUS(st) == 100) { printf("done: the SQL makes fewer than %ld allocations\n", n); break; }
    if (WIFSIGNALED(st)) { printf("CRASH at N=%ld (signal %d)\n", n, WTERMSIG(st)); crashes++; }
    else if (WIFEXITED(st) && WEXITSTATUS(st) != 0) {
      printf("CRASH at N=%ld (exit %d%s)\n", n, WEXITSTATUS(st),
             WEXITSTATUS(st) == 86 ? ", ASan" : WEXITSTATUS(st) == 87 ? ", UBSan" : ""); crashes++;
    }
  }
  printf("%ld crashing N value(s)\n", crashes);
  free(sql);
  return crashes ? 1 : 0;
}
