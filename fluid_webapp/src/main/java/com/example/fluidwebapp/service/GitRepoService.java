package com.example.fluidwebapp.service;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.UUID;

@Service
public class GitRepoService {
    private final String workDir = "/tmp/fluid-qa-branches";

    public GitRepoService() {
        try {
            Files.createDirectories(Paths.get(workDir));
        } catch (IOException e) {
            throw new RuntimeException("Failed to create work directory", e);
        }
    }

    public Mono<String> cloneRepository(String repoUrl, String branch, String githubPat) {
        String repoName = extractRepoName(repoUrl);
        String workPath = workDir + "/" + repoName + "-" + UUID.randomUUID();

        return Mono.fromCallable(() -> {
            Path path = Paths.get(workPath);
            Files.createDirectories(path);
            
            // Clone repo with authenticated URL
            String authUrl = repoUrl.replace("https://", "https://x-access-token:" + githubPat + "@");
            ProcessBuilder pb = new ProcessBuilder("git", "clone", "--branch", branch, authUrl, path.toString());
            pb.inheritIO();
            Process process = pb.start();
            int exitCode = process.waitFor();
            
            if (exitCode != 0) {
                throw new RuntimeException("Git clone failed with exit code " + exitCode);
            }
            
            return path.toString();
        });
    }

    public Mono<String> createQABranch(String repoPath, String ticketId) {
        String branchName = "qa/" + ticketId;

        return Mono.fromCallable(() -> {
            ProcessBuilder pb = new ProcessBuilder("git", "checkout", "-b", branchName);
            pb.directory(new java.io.File(repoPath));
            pb.inheritIO();
            Process process = pb.start();
            int exitCode = process.waitFor();
            
            if (exitCode != 0) {
                throw new RuntimeException("Branch creation failed");
            }
            
            return branchName;
        });
    }

    public Mono<String> commitAndPush(String repoPath, String message, String githubPat) {
        return Mono.fromCallable(() -> {
            // Commit
            ProcessBuilder pbCommit = new ProcessBuilder("git", "add", ".");
            pbCommit.directory(new java.io.File(repoPath));
            pbCommit.inheritIO();
            pbCommit.start().waitFor();

            ProcessBuilder pbMsg = new ProcessBuilder("git", "commit", "-m", message);
            pbMsg.directory(new java.io.File(repoPath));
            pbMsg.inheritIO();
            pbMsg.start().waitFor();

            // Push
            ProcessBuilder pbPush = new ProcessBuilder("git", "push", "origin", "HEAD");
            pbPush.directory(new java.io.File(repoPath));
            pbPush.inheritIO();
            Process process = pbPush.start();
            int exitCode = process.waitFor();

            if (exitCode != 0) {
                throw new RuntimeException("Push failed");
            }

            return "Changes pushed successfully";
        });
    }

    private String extractRepoName(String url) {
        return url.substring(url.lastIndexOf("/") + 1).replace(".git", "");
    }
}
