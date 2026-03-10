"""
Content Transformer Service
Converts newsletter content into LinkedIn posts using OpenAI API.
"""

import os
import re
from typing import Dict, Optional
from openai import OpenAI, OpenAIError, APITimeoutError, RateLimitError, AuthenticationError
import logging

from src.utils.logger import log_step_start, log_step_success, log_step_failure
from src.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class AITransformError(Exception):
    """Raised when AI transformation fails."""
    pass


class ContentTransformer:
    """
    Transforms newsletter content into LinkedIn posts using OpenAI GPT-4.
    """
    
    MAX_POST_LENGTH = 280
    MAX_CONTENT_CHARS = 1000
    API_TIMEOUT = 30
    MODEL = "gpt-4"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize ContentTransformer with OpenAI API key.
        
        Args:
            api_key: OpenAI API key. If None, reads from OPENAI_API_KEY env var.
            
        Raises:
            AITransformError: If API key is missing or invalid.
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        
        if not self.api_key:
            raise AITransformError("OpenAI API key not configured. Set OPENAI_API_KEY environment variable.")
        
        try:
            self.client = OpenAI(
                api_key=self.api_key,
                timeout=self.API_TIMEOUT
            )
        except Exception as e:
            raise AITransformError(f"Failed to initialize OpenAI client: {str(e)}")
    
    def _clean_content(self, content: str) -> str:
        """
        Clean and prepare content for AI processing.
        
        Args:
            content: Raw email content (HTML or text)
            
        Returns:
            Cleaned content string
        """
        if not content:
            return ""
        
        # Remove HTML tags
        content = re.sub(r'<[^>]+>', ' ', content)
        
        # Remove excessive whitespace
        content = re.sub(r'\s+', ' ', content)
        
        # Remove URLs (they'll be replaced with placeholder)
        content = re.sub(r'http[s]?://\S+', '[URL]', content)
        
        # Remove email addresses
        content = re.sub(r'\S+@\S+', '[EMAIL]', content)
        
        return content.strip()
    
    def _extract_hashtags(self, post_text: str) -> list:
        """
        Extract hashtags from post text.
        
        Args:
            post_text: LinkedIn post text
            
        Returns:
            List of hashtags (without # symbol)
        """
        hashtags = re.findall(r'#(\w+)', post_text)
        return hashtags
    
    def _build_prompt(self, content: str, subject: str, strict: bool = False) -> str:
        """
        Build prompt for OpenAI API.
        
        Args:
            content: Cleaned email content
            subject: Email subject line
            strict: If True, use stricter length constraints
            
        Returns:
            Formatted prompt string
        """
        if strict:
            return f"""Convert this newsletter into a LinkedIn post. STRICT REQUIREMENTS:
- EXACTLY {self.MAX_POST_LENGTH} characters or fewer
- Professional, engaging tone
- Include 2-3 relevant hashtags
- No URLs or promotional language
- Focus on key insights only

Subject: {subject}
Content: {content}

Generate ONLY the post text, nothing else."""
        
        return f"""Convert this newsletter excerpt into a professional LinkedIn post.

Requirements:
- Maximum {self.MAX_POST_LENGTH} characters (including spaces and hashtags)
- Professional, engaging tone suitable for LinkedIn
- Include 2-3 relevant hashtags at the end
- Focus on the most valuable insight or takeaway
- No URLs or overly promotional language

Subject: {subject}
Content: {content}

Generate ONLY the post text, nothing else."""
    
    @retry_with_backoff(
        max_attempts=3,
        base_delay=2,
        retryable_exceptions=(APITimeoutError, RateLimitError, ConnectionError)
    )
    def _call_openai_api(self, prompt: str) -> str:
        """
        Call OpenAI API with retry logic.
        
        Args:
            prompt: Formatted prompt
            
        Returns:
            Generated post text
            
        Raises:
            AITransformError: If API call fails
        """
        try:
            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional LinkedIn content creator. You transform newsletter content into engaging, concise LinkedIn posts."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=150
            )
            
            post_text = response.choices[0].message.content.strip()
            return post_text
            
        except AuthenticationError as e:
            raise AITransformError(f"Authentication failed: Invalid OpenAI API key - {str(e)}")
        except RateLimitError as e:
            logger.warning(f"Rate limit hit, will retry: {str(e)}")
            raise  # Let retry decorator handle it
        except APITimeoutError as e:
            logger.warning(f"API timeout, will retry: {str(e)}")
            raise  # Let retry decorator handle it
        except OpenAIError as e:
            raise AITransformError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            raise AITransformError(f"Unexpected error calling OpenAI API: {str(e)}")
    
    def transform_to_linkedin_post(
        self, 
        email_body: str, 
        subject: str
    ) -> Dict[str, any]:
        """
        Transform newsletter content into LinkedIn post.
        
        Args:
            email_body: Raw email body (HTML or text)
            subject: Email subject line
            
        Returns:
            Dict with keys:
                - post_text: Generated LinkedIn post
                - char_count: Character count
                - hashtags_used: List of hashtags
                
        Raises:
            AITransformError: If transformation fails
        """
        step_name = "ai_content_transformation"
        log_step_start(step_name, {
            "subject": subject,
            "content_length": len(email_body)
        })
        
        # Validate input
        if not email_body or not email_body.strip():
            error_msg = "Cannot transform empty content"
            log_step_failure(step_name, error_msg, None)
            raise AITransformError(error_msg)
        
        try:
            # Clean and truncate content
            cleaned_content = self._clean_content(email_body)
            truncated_content = cleaned_content[:self.MAX_CONTENT_CHARS]
            
            if len(cleaned_content) > self.MAX_CONTENT_CHARS:
                logger.info(f"Content truncated from {len(cleaned_content)} to {self.MAX_CONTENT_CHARS} chars")
            
            # First attempt with normal prompt
            prompt = self._build_prompt(truncated_content, subject, strict=False)
            post_text = self._call_openai_api(prompt)
            
            # Check length and retry if needed
            if len(post_text) > self.MAX_POST_LENGTH:
                logger.warning(
                    f"First attempt exceeded limit ({len(post_text)} chars), "
                    f"retrying with strict prompt"
                )
                
                strict_prompt = self._build_prompt(truncated_content, subject, strict=True)
                post_text = self._call_openai_api(strict_prompt)
                
                # Final length check
                if len(post_text) > self.MAX_POST_LENGTH:
                    # Forcefully truncate as last resort
                    logger.warning(
                        f"Strict attempt still exceeded limit, truncating to {self.MAX_POST_LENGTH} chars"
                    )
                    post_text = post_text[:self.MAX_POST_LENGTH - 3] + "..."
            
            # Extract hashtags
            hashtags = self._extract_hashtags(post_text)
            
            result = {
                "post_text": post_text,
                "char_count": len(post_text),
                "hashtags_used": hashtags
            }
            
            log_step_success(
                step_name,
                0,  # Duration tracked externally
                f"Generated {len(post_text)}-char post with {len(hashtags)} hashtags"
            )
            
            return result
            
        except AITransformError:
            raise  # Re-raise our custom errors
        except Exception as e:
            error_msg = f"Unexpected error during transformation: {str(e)}"
            log_step_failure(step_name, error_msg, str(e))
            raise AITransformError(error_msg)


# Convenience function for direct usage
def transform_newsletter_to_post(email_body: str, subject: str) -> Dict[str, any]:
    """
    Convenience function to transform newsletter to LinkedIn post.
    
    Args:
        email_body: Raw email body content
        subject: Email subject line
        
    Returns:
        Dict with post_text, char_count, and hashtags_used
        
    Raises:
        AITransformError: If transformation fails
    """
    transformer = ContentTransformer()
    return transformer.transform_to_linkedin_post(email_body, subject)
