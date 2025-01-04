import os
import json
import subprocess
import tempfile
from pathlib import Path
import logging
from typing import Dict, List, Optional, Tuple
import shutil

class GitHubAnalyzer:
    def __init__(self, repo_url: str, temp_dir: Optional[str] = None):
        """
        Initialize the GitHub analyzer
        
        Args:
            repo_url: GitHub repository URL
            temp_dir: Optional temporary directory path
        """
        self.repo_url = repo_url
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.logger = logging.getLogger(__name__)
        
        self.logger.debug(f"Initialized GitHubAnalyzer with repo: {repo_url}")
        self.logger.debug(f"Using temporary directory: {self.temp_dir}")
        
        # Validate repo URL format
        if not repo_url.startswith(('http://', 'https://', 'git://')):
            self.logger.warning(f"Repository URL {repo_url} may not be in a valid format")
        
    def clone_repository(self) -> Path:
        """Clone the GitHub repository to local temporary directory"""
        try:
            self.logger.info(f"Cloning repository: {self.repo_url}")
            # Use git clone command directly
            result = subprocess.run(
                ['git', 'clone', self.repo_url, self.temp_dir],
                capture_output=True,
                text=True,
                check=True
            )
            return Path(self.temp_dir)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Git clone failed: {e.stderr}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to clone repository: {str(e)}")
            raise

    def find_files(self, path: Path) -> Tuple[List[Path], List[Path]]:
        """
        Find code and documentation files in the repository
        
        Returns:
            Tuple containing lists of code and doc file paths
        """
        code_files = []
        doc_files = []
        
        # Common documentation files
        doc_patterns = {'.md', '.rst', '.txt', 'LICENSE', 'CONTRIBUTING', 'CODE_OF_CONDUCT'}
        # Code file extensions
        code_patterns = {'.py', '.js', '.java', '.cpp', '.go', '.rs', '.swift', '.kt', '.cs', '.toml'}
        # Binary file patterns to skip
        binary_patterns = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.zip', '.tar', '.gz'}
        
        try:
            for file_path in path.rglob('*'):
                if file_path.is_file():
                    # Skip binary files
                    if any(file_path.name.endswith(ext) for ext in binary_patterns):
                        self.logger.debug(f"Skipping binary file: {file_path}")
                        continue
                        
                    # 构造相对于temp_dir的路径
                    relative_path = file_path.relative_to(path)
                    temp_dir_path = Path(self.temp_dir) / relative_path
                    
                    self.logger.debug(f"Processing file: {temp_dir_path}")
                    
                    if any(file_path.name.endswith(ext) for ext in code_patterns):
                        code_files.append(temp_dir_path)
                        self.logger.info(f"Added code file: {relative_path}")
                    elif any(file_path.name.endswith(ext) or file_path.name == name 
                           for ext in doc_patterns for name in doc_patterns):
                        doc_files.append(temp_dir_path)
                        self.logger.info(f"Added doc file: {relative_path}")
        except Exception as e:
            self.logger.error(f"Error finding files: {str(e)}")
            raise
                    
        return code_files, doc_files

    def generate_file_prompts(self, file_paths: List[Path]) -> Dict[str, str]:
        """
        Generate prompts for each file using code2prompt
        
        Args:
            file_paths: List of file paths to process
            
        Returns:
            Dictionary mapping file paths to generated prompts
        """
        prompts = {}
        for file_path in file_paths:
            self.logger.debug(f"Generating prompt for: {file_path}")
            
            # 获取相对于temp_dir的路径作为key
            try:
                relative_key = file_path.relative_to(Path(self.temp_dir))
            except ValueError:
                relative_key = file_path.name
                
            key = str(relative_key)
            self.logger.debug(f"Using key: {key}")
            
            # 创建临时输出文件
            output_file = Path(self.temp_dir) / f"{relative_key}.prompt.txt"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                # First check if code2prompt is installed
                try:
                    # Run code2prompt for each file with output parameter
                    self.logger.info(f"Attempting to use code2prompt for {relative_key}")
                    result = subprocess.run(
                        ['code2prompt', str(file_path), f'--output={output_file}'],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    # 从输出文件读取生成的prompt
                    if output_file.exists():
                        with open(output_file, 'r', encoding='utf-8') as f:
                            prompts[key] = f.read()
                        self.logger.info(f"Successfully generated prompt using code2prompt for {relative_key}")
                    else:
                        self.logger.warning(f"Output file not found for {relative_key}, using command output")
                        prompts[key] = result.stdout
                except FileNotFoundError:
                    # If code2prompt is not installed, just read the file content
                    self.logger.info(f"code2prompt not found, reading raw content for {relative_key}")
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            prompts[key] = f.read()
                        self.logger.info(f"Successfully read raw content for {relative_key}")
                    except UnicodeDecodeError:
                        self.logger.warning(f"Could not read {relative_key} as text file, skipping")
                        continue
            except Exception as e:
                self.logger.error(f"Error processing {relative_key}: {str(e)}")
                if not any(marker in str(e) for marker in ['binary', 'UnicodeDecodeError']):
                    # Only add error message for non-binary files
                    prompts[key] = f"Error processing file: {str(e)}"
            finally:
                # 清理临时输出文件
                if output_file.exists():
                    try:
                        output_file.unlink()
                    except Exception as e:
                        self.logger.warning(f"Failed to clean up temporary file {output_file}: {str(e)}")
                        
        return prompts


    def generate_file_tree(self, path: Path) -> Dict:
        """Generate a dictionary representing the repository file tree"""
        def _build_tree(path: Path) -> Dict:
            tree = {}
            try:
                for item in path.iterdir():
                    if item.name.startswith('.'):
                        continue
                    if item.is_file():
                        tree[item.name] = str(item)
                    elif item.is_dir():
                        subtree = _build_tree(item)
                        if subtree:  # Only add non-empty directories
                            tree[item.name] = subtree
            except Exception as e:
                self.logger.error(f"Error building tree for {path}: {str(e)}")
            return tree
            
        return _build_tree(path)

    def analyze(self) -> Dict:
        """
        Analyze the GitHub repository and return formatted results
        
        Returns:
            Dictionary containing file tree, documentation and code analysis
        """
        try:
            # Clone repository
            repo_path = self.clone_repository()
            
            # Find files
            code_files, doc_files = self.find_files(repo_path)
            
            # Generate prompts
            code_prompts = self.generate_file_prompts(code_files)
            doc_prompts = self.generate_file_prompts(doc_files)
            
            # Generate file tree
            file_tree = self.generate_file_tree(repo_path)
            
            # Format results
            result = {
                "filetree": file_tree,
                "doc": doc_prompts,
                "code": code_prompts
            }
            
            return result
        finally:
            # Cleanup temporary directory
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)

def main():
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Example usage
    repo_url = "https://github.com/username/repo"
    analyzer = GitHubAnalyzer(repo_url)
    
    try:
        result = analyzer.analyze()
        
        # Pretty print results
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        logging.error(f"Analysis failed: {str(e)}")

if __name__ == "__main__":
    # Set up command line argument parsing
    import argparse
    parser = argparse.ArgumentParser(description='GitHub Repository Analyzer')
    parser.add_argument('--repo', type=str, help='GitHub repository URL to analyze')
    parser.add_argument('--log-level', 
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                      default='INFO',
                      help='Set the logging level')
    args = parser.parse_args()

    # Setup logging with user-specified level
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # If no repo URL is provided, use the default one
    repo_url = args.repo or "https://github.com/username/repo"
    
    analyzer = GitHubAnalyzer(repo_url)
    try:
        result = analyzer.analyze()
        print(json.dumps(result, indent=2))
    except Exception as e:
        logging.error(f"Analysis failed: {str(e)}")