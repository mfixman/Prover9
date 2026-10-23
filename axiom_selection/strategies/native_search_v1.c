#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static double now(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec + t.tv_nsec * 1e-9;
}

static pid_t launch(const char *binary, const char *input, int *reader) {
  int channel[2];
  if (pipe(channel)) return -1;
  pid_t pid = fork();
  if (pid == 0) {
    int fd = open(input, O_RDONLY);
    if (fd < 0) _exit(126);
    dup2(fd, STDIN_FILENO);
    dup2(channel[1], STDOUT_FILENO);
    dup2(channel[1], STDERR_FILENO);
    close(fd);
    close(channel[0]);
    close(channel[1]);
    execl(binary, binary, (char *) NULL);
    _exit(127);
  }
  close(channel[1]);
  *reader = channel[0];
  return pid;
}

static int collect(int reader, FILE *log, double deadline) {
  char buffer[65536 + 128], tail[128] = "";
  struct pollfd descriptor = {reader, POLLIN, 0};
  while (now() < deadline) {
    int milliseconds = (int) ((deadline - now()) * 1000);
    if (milliseconds < 1) milliseconds = 1;
    int ready = poll(&descriptor, 1, milliseconds);
    if (ready < 0 && errno == EINTR) continue;
    if (ready <= 0) break;
    size_t prefix = strlen(tail);
    memcpy(buffer, tail, prefix);
    ssize_t n = read(reader, buffer + prefix, 65535);
    if (n <= 0) break;
    fwrite(buffer + prefix, 1, n, log);
    buffer[prefix + n] = 0;
    if (strstr(buffer, "============================== end of proof") ||
        strstr(buffer, "THEOREM PROVED")) return 1;
    size_t length = prefix + n;
    size_t retained = length < 127 ? length : 127;
    memcpy(tail, buffer + length - retained, retained);
    tail[retained] = 0;
  }
  return 0;
}

int main(int argc, char **argv) {
  if (argc != 5) {
    fprintf(stderr, "Usage: native-search BINARY INPUT LOG SECONDS\n");
    return 2;
  }
  double seconds = strtod(argv[4], NULL), started = now();
  FILE *log = fopen(argv[3], "w");
  if (!log || seconds <= 0) return 2;
  int reader, status;
  pid_t pid = launch(argv[1], argv[2], &reader);
  if (pid < 0) return 2;
  int proved = collect(reader, log, started + seconds);
  kill(pid, SIGKILL);
  struct rusage usage;
  while (wait4(pid, &status, 0, &usage) < 0 && errno == EINTR) {}
  close(reader);
  fclose(log);
  double cpu = usage.ru_utime.tv_sec + usage.ru_utime.tv_usec * 1e-6;
  cpu += usage.ru_stime.tv_sec + usage.ru_stime.tv_usec * 1e-6;
  printf("{\"proved\":%s,\"search_s\":%.9f,\"cpu_s\":%.9f,\"exit\":%d}\n",
         proved ? "true" : "false", now() - started, cpu,
         WIFEXITED(status) ? WEXITSTATUS(status) : -WTERMSIG(status));
  return 0;
}
